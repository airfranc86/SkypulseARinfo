# Auditoría técnica / Lista de tareas pendientes  
**Fecha:** 26-05-2026  

---

## 🎯 Rol esperado

Actuá como **agente técnico de auditoría + organización de tareas**.

Tu objetivo es:
- Auditar el problema descripto
- Detectar posibles causas técnicas
- Proponer verificaciones concretas
---

## 🚨 Problemas actuales

### 1. Backend → terremotos
El backend **no está devolviendo el terremoto más reciente**.

Caso concreto:
- Fecha: 26-05-2026  
- ID EMSC: `2000865`  
- URL: https://www.emsc-csem.org/Earthquake_information/earthquake.php?id=2000865  

---

### 2. Frontend → header no interactivo

El header:
- No tiene scroll (horizontal) solo un efecto visual en bucle infinito.
- Pero **NO responde a interacción**
  - No se puede hacer scroll manual (mouse o touch)
  - No se puede hacer click ni arrastrar

---

## 🔍 Tareas de auditoría requeridas

### 1. Backend — Terremotos

Auditá y generá tareas para verificar:

- Fuente de datos:
  - ¿Se consulta directamente EMSC o hay intermediarios?
- Lógica de filtrado:
  - Fecha / hora
  - Magnitud
  - Región
- Manejo de caché:
  - ¿Se están devolviendo datos viejos?
- Pipeline backend → frontend:
  - ¿El JSON expuesto contiene realmente el último registro?

---

### 2. Frontend — Header

Auditá y generá tareas para verificar:

- Implementación del componente:
  - `<div>` con overflow
  - Librería externa (swiper, slick, etc.)
- CSS que pueda bloquear interacción:
  - `pointer-events`
  - `touch-action`
  - `overflow`
  - `user-select`
- Eventos JS:
  - scroll
  - touchstart / touchmove
- Contenedores padre que puedan estar bloqueando el comportamiento

---

## ✅ Formato de salida obligatorio

### A) Lista de tareas de auditoría

- Separada en:
  1. Backend (terremotos / FastAPI)
  2. Frontend (header / React)

- Cada ítem debe ser:
  - Acción concreta
  - Corta
  - Ejecutable

✔ Ejemplo correcto:
- Verificar el rango de fechas enviado a la API de EMSC  

✘ Ejemplo incorrecto:
- Revisar si hay problemas con fechas  

---

### B) Posibles causas + pruebas rápidas

Para cada problema:

- Lista breve de causas probables
- 1–2 pruebas rápidas para validar hipótesis

Ejemplos de pruebas:
- cURL / Postman contra el backend  
- Desactivar CSS específico  
- Reemplazar componente por uno mínimo (`overflow: auto`)  

---

## 🧠 Criterio de trabajo

- Priorizar **impacto + probabilidad**
- Evitar teoría innecesaria
- Ir a lo verificable
- Pensar como alguien que va a ejecutar estas tareas ahora mismo

---

## 🎯 Resultado esperado

Una salida que:
- Sea clara
- Sea accionable
- Reduzca la ambigüedad
- Permita avanzar sin tener que reinterpretar nada