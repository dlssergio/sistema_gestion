📌 Estructura del proyecto

El proyecto está dividido en dos repositorios independientes:

Proyectos/
├─ sistema_gestion   → Backend (Django / AFIP / Stock / Ventas)
└─ frontend          → Frontend (POS / Administración)


Ambos repositorios evolucionan en paralelo.

🌿 Estrategia de ramas

main
Rama estable. Solo recibe cambios vía merge.

feature/*
Ramas de desarrollo para nuevas funcionalidades.

👉 Regla clave
Cuando una funcionalidad afecta frontend y backend, usar el MISMO nombre de rama en ambos repositorios.

Ejemplo:

feature/stock-cae-automatizacion

🔁 Flujo de trabajo estándar (paso a paso)
1️⃣ Crear rama nueva (en ambos repos)
Backend
cd sistema_gestion
git checkout main
git pull origin main
git checkout -b feature/nombre-feature

Frontend
cd ../frontend
git checkout main
git pull origin main
git checkout -b feature/nombre-feature

2️⃣ Desarrollo

Backend: modelos, servicios, AFIP, stock, lógica de negocio

Frontend: vistas, POS, flujos de usuario

Se puede trabajar alternando entre repositorios sin problema.

3️⃣ Subir cambios
Backend
git add .
git commit -m "Backend: descripción clara del cambio"
git push origin feature/nombre-feature

Frontend
git add .
git commit -m "Frontend: descripción clara del cambio"
git push origin feature/nombre-feature

4️⃣ Impactar en main

Para cada repositorio:

Crear Pull Request:

base: main
compare: feature/nombre-feature


Mergear

(Opcional) borrar la rama feature

🚫 Qué NO hacer

❌ Trabajar directamente sobre main

❌ Mezclar frontend y backend en un mismo repo

❌ Usar nombres de ramas distintos para el mismo feature

❌ Confiar solo en la vista “Code” de GitHub para validar cambios

✅ Principios del flujo

Claridad antes que rapidez

Features trazables en frontend y backend

Git como herramienta de respaldo, no de estrés

📅 Última actualización

Autor: Sergio de los Santos
Proyecto: Sistema de Gestión
Estado: Activo
