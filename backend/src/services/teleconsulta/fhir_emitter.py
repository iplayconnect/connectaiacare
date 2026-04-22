"""FHIR R4 Emitter — converte SOAP + metadata da consulta em FHIR Bundle.

Determinístico (não usa LLM). Gera estrutura HL7 FHIR R4 pra interop com
qualquer EHR/hospital/operadora.

Recursos gerados:
    - Encounter: a consulta em si
    - Patient: paciente (espelho do nosso DB)
    - Practitioner: médico que atendeu
    - Observation: vitais mencionados ou referenciados
    - Condition: diagnósticos/problemas confirmados
    - MedicationStatement: medicações em uso
    - MedicationRequest: medicações prescritas na consulta
    - ServiceRequest: exames solicitados
    - ClinicalImpression: resumo clínico

Referência: https://www.hl7.org/fhir/R4/
ADR-023 §Implementation, ADR-011 (locale PT-BR), ADR-014 (vitais LOINC)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def emit_bundle(
    teleconsultation: dict[str, Any],
    patient: dict[str, Any],
    doctor: dict[str, Any],
    soap: dict[str, Any],
) -> dict[str, Any]:
    """Gera FHIR Bundle do tipo 'document' a partir dos dados da consulta.

    Args:
        teleconsultation: row da tabela aia_health_teleconsultations
        patient: row da tabela aia_health_patients
        doctor: row da tabela aia_health_doctors (pode ser None em demo)
        soap: JSON do SOAP (output do soap_writer)

    Returns:
        Dict no formato FHIR Bundle R4 serializável em JSON.
    """
    bundle_id = str(uuid.uuid4())
    encounter_id = str(teleconsultation["id"])
    patient_fhir_id = f"pat-{str(patient['id']).replace('-','')[:16]}"
    practitioner_fhir_id = (
        f"prac-{str(doctor['id']).replace('-','')[:16]}" if doctor else "prac-demo"
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    started = _iso(teleconsultation.get("started_at")) or now_iso
    ended = _iso(teleconsultation.get("ended_at")) or now_iso

    entries: list[dict] = [
        # Patient
        {
            "fullUrl": f"urn:uuid:{patient_fhir_id}",
            "resource": _build_patient(patient_fhir_id, patient),
            "request": {"method": "PUT", "url": f"Patient/{patient_fhir_id}"},
        },
        # Practitioner
        {
            "fullUrl": f"urn:uuid:{practitioner_fhir_id}",
            "resource": _build_practitioner(practitioner_fhir_id, doctor),
            "request": {"method": "PUT", "url": f"Practitioner/{practitioner_fhir_id}"},
        },
        # Encounter (a consulta)
        {
            "fullUrl": f"urn:uuid:{encounter_id}",
            "resource": _build_encounter(
                encounter_id, patient_fhir_id, practitioner_fhir_id, started, ended,
                teleconsultation,
            ),
            "request": {"method": "POST", "url": "Encounter"},
        },
    ]

    # Conditions (diagnósticos + problemas novos identificados)
    assessment = soap.get("assessment") or {}
    for idx, cond in enumerate(assessment.get("active_problems_confirmed") or []):
        cond_id = f"cond-{encounter_id[:8]}-{idx}"
        entries.append({
            "fullUrl": f"urn:uuid:{cond_id}",
            "resource": _build_condition(
                cond_id, patient_fhir_id, encounter_id,
                description=cond, clinical_status="active",
            ),
            "request": {"method": "POST", "url": "Condition"},
        })

    primary = assessment.get("primary_hypothesis")
    if primary and primary.get("description"):
        cond_id = f"cond-{encounter_id[:8]}-primary"
        entries.append({
            "fullUrl": f"urn:uuid:{cond_id}",
            "resource": _build_condition(
                cond_id, patient_fhir_id, encounter_id,
                description=primary["description"],
                clinical_status="active",
                verification_status="provisional",  # hipótese, não confirmado
                cid10=primary.get("cid10_suggestion"),
                note="Hipótese principal sugerida por IA, revisada pelo médico.",
            ),
            "request": {"method": "POST", "url": "Condition"},
        })

    # MedicationRequests (medicações novas prescritas na consulta)
    plan = soap.get("plan") or {}
    meds_plan = plan.get("medications") or {}
    for idx, med in enumerate(meds_plan.get("started") or []):
        med_id = f"med-{encounter_id[:8]}-new-{idx}"
        entries.append({
            "fullUrl": f"urn:uuid:{med_id}",
            "resource": _build_medication_request(
                med_id, patient_fhir_id, encounter_id, practitioner_fhir_id,
                medication=med.get("medication", ""),
                dose=med.get("dose", ""),
                schedule=med.get("schedule", ""),
                duration=med.get("duration", ""),
                status="active",
            ),
            "request": {"method": "POST", "url": "MedicationRequest"},
        })

    # ServiceRequests (exames solicitados)
    for idx, test in enumerate(plan.get("diagnostic_tests_requested") or []):
        sr_id = f"sr-{encounter_id[:8]}-{idx}"
        entries.append({
            "fullUrl": f"urn:uuid:{sr_id}",
            "resource": _build_service_request(
                sr_id, patient_fhir_id, encounter_id, practitioner_fhir_id,
                test=test.get("test", ""),
                urgency=test.get("urgency", "routine"),
                reason=test.get("reason", ""),
            ),
            "request": {"method": "POST", "url": "ServiceRequest"},
        })

    # ClinicalImpression (resumo clínico integrado)
    ci_id = f"ci-{encounter_id[:8]}"
    entries.append({
        "fullUrl": f"urn:uuid:{ci_id}",
        "resource": _build_clinical_impression(
            ci_id, patient_fhir_id, encounter_id, practitioner_fhir_id, soap,
        ),
        "request": {"method": "POST", "url": "ClinicalImpression"},
    })

    return {
        "resourceType": "Bundle",
        "id": bundle_id,
        "type": "transaction",
        "timestamp": now_iso,
        "meta": {
            "source": "https://demo.connectaia.com.br",
            "tag": [
                {
                    "system": "https://connectaia.com.br/fhir/tags",
                    "code": "teleconsultation",
                    "display": "Teleconsulta ConnectaIACare",
                }
            ],
        },
        "entry": entries,
    }


# -----------------------------------------------------------------
# Builders
# -----------------------------------------------------------------
def _build_patient(fhir_id: str, patient: dict) -> dict:
    full_name = patient.get("full_name") or ""
    name_parts = full_name.split()
    family = name_parts[-1] if name_parts else ""
    given = name_parts[:-1] if len(name_parts) > 1 else name_parts

    resource = {
        "resourceType": "Patient",
        "id": fhir_id,
        "active": True,
        "name": [{
            "use": "official",
            "text": full_name,
            "family": family,
            "given": given,
        }],
    }
    if patient.get("birth_date"):
        resource["birthDate"] = str(patient["birth_date"]).split("T")[0]
    if patient.get("gender"):
        gender_map = {"M": "male", "F": "female", "O": "other"}
        resource["gender"] = gender_map.get(patient["gender"], "unknown")
    if patient.get("external_id"):
        resource["identifier"] = [{
            "system": "https://totalcare-vidafone.contactto.care/fhir/patient-id",
            "value": str(patient["external_id"]),
        }]
    return resource


def _build_practitioner(fhir_id: str, doctor: dict | None) -> dict:
    if not doctor:
        return {
            "resourceType": "Practitioner",
            "id": fhir_id,
            "active": True,
            "name": [{"text": "Médico de demonstração (não identificado)"}],
        }
    full_name = doctor.get("full_name") or "Médico"
    name_parts = full_name.split()
    family = name_parts[-1] if name_parts else ""
    given = name_parts[:-1] if len(name_parts) > 1 else name_parts

    resource = {
        "resourceType": "Practitioner",
        "id": fhir_id,
        "active": bool(doctor.get("active", True)),
        "name": [{
            "use": "official",
            "text": full_name,
            "family": family,
            "given": given,
        }],
    }
    if doctor.get("crm_number"):
        resource["identifier"] = [{
            "system": f"https://cfm.org.br/crm/{(doctor.get('crm_state') or 'BR').lower()}",
            "value": doctor["crm_number"],
        }]
    if doctor.get("specialties"):
        resource["qualification"] = [
            {"code": {"text": s}} for s in doctor["specialties"]
        ]
    return resource


def _build_encounter(
    enc_id: str, patient_ref: str, practitioner_ref: str,
    started_iso: str, ended_iso: str, teleconsultation: dict,
) -> dict:
    return {
        "resourceType": "Encounter",
        "id": enc_id,
        "status": "finished",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "VR",  # Virtual (Telehealth)
            "display": "virtual",
        },
        "type": [{
            "coding": [{
                "system": "http://snomed.info/sct",
                "code": "448337001",
                "display": "Telemedicine consultation with patient",
            }],
            "text": "Teleconsulta",
        }],
        "subject": {"reference": f"Patient/{patient_ref}"},
        "participant": [{
            "type": [{
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ParticipationType",
                    "code": "ATND",
                    "display": "attender",
                }],
            }],
            "individual": {"reference": f"Practitioner/{practitioner_ref}"},
        }],
        "period": {"start": started_iso, "end": ended_iso},
    }


def _build_condition(
    cond_id: str, patient_ref: str, encounter_ref: str, description: str,
    clinical_status: str = "active",
    verification_status: str = "confirmed",
    cid10: str | None = None,
    note: str | None = None,
) -> dict:
    resource: dict[str, Any] = {
        "resourceType": "Condition",
        "id": cond_id,
        "clinicalStatus": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                "code": clinical_status,
            }],
        },
        "verificationStatus": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                "code": verification_status,
            }],
        },
        "code": {"text": description},
        "subject": {"reference": f"Patient/{patient_ref}"},
        "encounter": {"reference": f"Encounter/{encounter_ref}"},
    }
    if cid10:
        # Extrai só o código se veio "I10 - Hipertensão"
        code_only = cid10.split(" ")[0].strip() if cid10 else None
        if code_only:
            resource["code"]["coding"] = [{
                "system": "http://hl7.org/fhir/sid/icd-10",
                "code": code_only,
                "display": cid10,
            }]
    if note:
        resource["note"] = [{"text": note}]
    return resource


def _build_medication_request(
    med_id: str, patient_ref: str, encounter_ref: str, practitioner_ref: str,
    medication: str, dose: str, schedule: str, duration: str,
    status: str = "active",
) -> dict:
    instruction = f"{dose} · {schedule}"
    if duration:
        instruction += f" · por {duration}"

    return {
        "resourceType": "MedicationRequest",
        "id": med_id,
        "status": status,
        "intent": "order",
        "medicationCodeableConcept": {"text": medication or "(a especificar)"},
        "subject": {"reference": f"Patient/{patient_ref}"},
        "encounter": {"reference": f"Encounter/{encounter_ref}"},
        "requester": {"reference": f"Practitioner/{practitioner_ref}"},
        "authoredOn": datetime.now(timezone.utc).isoformat(),
        "dosageInstruction": [{
            "text": instruction,
            "patientInstruction": instruction,
        }],
    }


def _build_service_request(
    sr_id: str, patient_ref: str, encounter_ref: str, practitioner_ref: str,
    test: str, urgency: str, reason: str,
) -> dict:
    priority_map = {"routine": "routine", "rotina": "routine", "urgent": "urgent", "urgente": "urgent"}
    return {
        "resourceType": "ServiceRequest",
        "id": sr_id,
        "status": "active",
        "intent": "order",
        "priority": priority_map.get((urgency or "").lower(), "routine"),
        "code": {"text": test or "(a especificar)"},
        "subject": {"reference": f"Patient/{patient_ref}"},
        "encounter": {"reference": f"Encounter/{encounter_ref}"},
        "requester": {"reference": f"Practitioner/{practitioner_ref}"},
        "reasonCode": [{"text": reason}] if reason else [],
        "authoredOn": datetime.now(timezone.utc).isoformat(),
    }


def _build_clinical_impression(
    ci_id: str, patient_ref: str, encounter_ref: str, practitioner_ref: str,
    soap: dict,
) -> dict:
    subjective = (soap.get("subjective") or {}).get("history_of_present_illness", "")
    assessment = (soap.get("assessment") or {})
    reasoning = assessment.get("clinical_reasoning", "")
    plan_text_parts = []
    plan = soap.get("plan") or {}
    if plan.get("non_pharmacological"):
        plan_text_parts.append("Orientações: " + "; ".join(plan["non_pharmacological"]))
    if plan.get("return_follow_up", {}).get("when"):
        plan_text_parts.append(f"Retorno: {plan['return_follow_up']['when']}")

    summary = "\n\n".join([
        subjective,
        f"Avaliação: {reasoning}",
        " • ".join(plan_text_parts) if plan_text_parts else "",
    ]).strip()

    return {
        "resourceType": "ClinicalImpression",
        "id": ci_id,
        "status": "completed",
        "subject": {"reference": f"Patient/{patient_ref}"},
        "encounter": {"reference": f"Encounter/{encounter_ref}"},
        "assessor": {"reference": f"Practitioner/{practitioner_ref}"},
        "date": datetime.now(timezone.utc).isoformat(),
        "summary": summary or "Teleconsulta realizada. Ver recursos relacionados.",
    }


def _iso(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, str):
        return value
    try:
        return value.isoformat()
    except Exception:
        return None
