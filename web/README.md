# Personal Balance — versión web (Python)

Misma app que la del iPhone, hecha con **Flask**. Usa la **misma cuenta y los mismos datos**
de Firebase (`users/{uid}/data/estado` y `perfil`), así que lo que cambies aquí aparece en el
iPhone y al revés.

**Fase 1:** cuentas (correo/contraseña y Google), Resumen, Gastos mensuales, Préstamos,
Perfil (foto, icono, nombre, tema, idioma) y Datos (copia de seguridad).
**Fase 2 (pendiente):** Inversiones (cartera, seguimiento, IBKR, precios).

## Cómo funciona
- El navegador inicia sesión con Firebase Auth y guarda el token en la cookie `pb_token`.
- El servidor Python verifica el token (`firebase_admin.auth.verify_id_token`) y lee/escribe
  Firestore con el Admin SDK. Todos los cálculos (préstamos, cuotas, gráficos) están en `calc.py`.

## Probar en tu ordenador (sin Firebase)
```
pip install -r requirements.txt
PB_DEV=1 python app.py      # abre http://localhost:8080 y pulsa "Entrar (modo prueba)"
```

## Publicar
Se publica sola en Google Cloud Run con GitHub Actions (`.github/workflows/deploy-web.yml`)
cada vez que cambia algo en `web/`, usando el secreto `FIREBASE_SERVICE_ACCOUNT`.
