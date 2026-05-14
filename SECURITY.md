# Security — History Rewrite Notice

## Historial reescrito el 2026-05-14

El branch `refactor/modular-arch` fue reescrito usando `git filter-repo`
para eliminar archivos sensibles que fueron commiteados por error en versiones
anteriores del repositorio.

### Archivos eliminados del historial

- `.env`, `.env.bak`, `.env.bak.1757617888`, `.env.example.bak`
- `veta.cookies`
- `ticks_export.csv`
- `data/wsbonos.sqlite3`, `data/wsbonos.sqlite3-shm`, `data/wsbonos.sqlite3-wal`
- `data/wsbonos.sqlite3.bak.2025-09-08_202755`
- `backups/` (directorio completo)

### Por qué se hizo

Credenciales de acceso a la API de Veta y archivos de base de datos local
quedaron trackeados en commits anteriores. El historial fue purgado para evitar
que esos datos sensibles permanezcan accesibles públicamente en GitHub.

### Acción requerida para cualquier clone previo al 2026-05-14

**NO uses `git pull`, `git fetch`, ni `git rebase`** — tu historial local
diverge del remoto y no puede reconciliarse.

El único camino correcto es re-clonar desde cero:

```bash
# 1. Guardá cualquier trabajo local sin pushear
# 2. Eliminá el clone viejo
cd ..
rm -rf ws-bonos

# 3. Cloná fresh desde origin
git clone git@github.com:cadete74/ws-bonos.git
cd ws-bonos

# 4. Copiá tu .env (si lo tenías fuera del repo)
cp /ruta/a/tu/.env.local ws-bonos/.env
```

### Estado actual del repositorio

- `.gitignore` actualizado para bloquear todos los patrones sensibles
- `.env.example` contiene únicamente placeholders — copiarlo como `.env` y completar
- El tag local `pre-purge-backup` apunta al estado previo al purge (retención 30 días)
- El mirror de backup local existe en `../ws-bonos.git.backup-20260514-132801/`

### Referencia de cambio

Change ID: `security-creds-purge`
Ejecutado el: 2026-05-14
