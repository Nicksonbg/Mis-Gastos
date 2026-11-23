# Pendientes — Personal Balance

Lista de cosas anotadas para hacer más adelante. No son fallos ni urgencias.

## Seguridad (endurecimiento, opcional)

- [ ] **"Pro" decidido en el servidor.** Cuando se construya la versión de pago,
  el estado `pro` (sí/no) debe marcarse y comprobarse **en el servidor** (al pagar,
  o al activarlo el admin), nunca fiándose de lo que mande el cliente. Motivo: al
  importar datos se conservan campos extra, así que un cliente no debe poder
  ponerse el `pro` a mano para desbloquear gratis.
- [ ] **CSP más estricta (con `script-src`).** Red de seguridad extra contra XSS
  futuros. Requiere trabajo porque la app usa scripts en línea (habría que usar
  nonces o mover el JS). Para cuando haya tiempo.

## Hecho

- [x] (2026-11-23) Foto de perfil: solo imágenes subidas, sin enlaces externos ni SVG.
- [x] (2026-11-23) Auditoría de seguridad completa (SSRF, XSS, inyección, CSRF, IDOR,
  subida de archivos, redirecciones, cabeceras, secretos): sin vulnerabilidades abiertas.
- [x] (2026-11) Copias de seguridad de Firestore (PITR + diaria + semanal).
- [x] (2026-11) Aviso de gasto en Google Cloud (5 €).
- [x] (2026-11) Registro de errores + avisos al admin + resumen diario.
- [x] (2026-11) Política de privacidad.

## Ideas por decidir (del plan Pro)

- Modelo freemium: gratis útil + 10 escaneos/mes; **Pro 1,99 € (pago único)** = todo
  ilimitado (uso justo, con tope oculto anti-abuso). Admin puede regalar Pro.
- Función "Mis documentos": avisos de caducidad de DNI/pasaporte/carnet (lectura de la
  fecha en el móvil, sin guardar la imagen). Tarjetas de banco: fuera (ya avisa el banco).
- Posible nicho: gestión de vida para personas que viven fuera de su país.
