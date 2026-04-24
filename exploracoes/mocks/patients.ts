/**
 * Mock canônico — RE-EXPORT de frontend/src/mocks/patients.ts
 *
 * O arquivo original foi movido pra dentro de frontend/src/ porque
 * o Dockerfile do frontend só copia frontend/ pro build (exploracoes/
 * fica fora do contexto Docker).
 *
 * Para Opus Design: pode continuar referenciando `exploracoes/mocks/patients.ts`
 * como fonte — este arquivo re-exporta tudo do frontend automaticamente.
 *
 * Quando editar o mock, edite SEMPRE em `frontend/src/mocks/patients.ts`.
 */
export * from "../../frontend/src/mocks/patients";
