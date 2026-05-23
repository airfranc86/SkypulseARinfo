# Autenticación GitHub CLI + instalación skill log-analysis

## Contexto
El skill `supercent-io/skills-template@log-analysis` (10.6K installs) complementa
los agents `systematic-debugging` y `error-detective` para análisis de logs de Render.
Requiere que `gh` esté autenticado en la sesión de Claude Code.

## Pasos

### 1. Autenticar gh CLI
En el prompt de Claude Code, escribí:
```
! gh auth login
```
Cuando pregunte:
- **What account?** → `GitHub.com`
- **Protocol?** → `HTTPS`
- **Authenticate?** → `Login with a web browser`

Copiá el código de 8 caracteres que aparece (formato `XXXX-XXXX`).
Abrí `https://github.com/login/device`, pegá el código, autorizá.

### 2. Verificar auth
```
! gh auth status
```
Debe mostrar: `✓ Logged in as airfranc86`

### 3. Instalar el skill
```
! npx skills add supercent-io/skills-template@log-analysis --global
```

### 4. Verificar instalación
```
! npx skills list
```

## Uso posterior
Una vez instalado, podés correrlo contra logs de Render con:
```
/log-analysis
```
y pegando los logs del dashboard de Render.
