# Integración FeatureUnivision → SkypulseAR (C)

**Estado**: Documentación + endpoint (`FeatureUnivision/app.py`) creado. **No se modificaron archivos de producción de SkypulseAR** sin confirmación del archivo exacto.

## ¿Qué archivo modificar en SkypulseAR?

Según la estructura de `SkypulseAR/apps/` (Next.js / Vercel), las opciones seguras son:

| Opción | Archivo sugerido | Impacto en producción |
|---|---|---|
| A. **Página dedicada** | `SkypulseAR/apps/pages/univision.tsx` (o `.tsx` equivalente en `pages/`) | Bajo: nueva ruta `/univision`, no altera otras páginas. |
| B. **Componente embebido** | `SkypulseAR/apps/components/ForecastPanel.tsx` + referencia en página existente | Medio: modifica componente existente; requiere revisión visual. |
| C. **API proxy** | `SkypulseAR/apps/api/univision/route.ts` (o `.ts` en el router existente) que hace `fetch('http://localhost:8082/forecast/latest')` | Bajo-medio: agrega endpoint interno; no toca UI directamente. |

**Recomendación**: empezar con **A** (nueva página) para evitar riesgos en producción, luego migrar a B o C según uso.

## Endpoint creado (`FeatureUnivision/app.py`)

- `http://localhost:8082/forecast/latest` → JSON con el forecast más reciente.
- `http://localhost:8082/forecast/alerts` → JSON con la última alerta.
- `GET /` → status básico.

## Pasos para completar C (cuando el usuario lo autorice explícitamente)

1. Copiar `FeatureUnivision/app.py` a un subdirectorio del deploy de Vercel si se quiere un servicio independiente.
2. Si se quiere integrar en `SkypulseAR/apps/pages/univision.tsx`:
   - Crear componente que llame al endpoint (proxy interno o externo).
   - Importar `forecast_report.md` como evidencia o mostrar el JSON de `/forecast/latest`.
3. Actualizar `SkypulseAR/vercel.json` si se agrega ruta personalizada (`/univision` → `FeatureUnivision/app.py`).
4. No modificar `CLAUDE.md` ni `README.md` sin pedido explícito adicional.

## Riesgo de integración actual

- `SkypulseAR` usa TypeScript (no Python); `FeatureUnivision` es Python + PIL; la integración es vía endpoint HTTP, no importación directa.
- `segmentation_agent.py` aún es stub (`stub_heuristic_v0`); reemplazar con ACLNet antes de usar en producción.
- `LLM` en forecast_agent es opcional (`--try-llm`); por defecto usa rules (seguro para producción).
