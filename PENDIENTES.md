# Pendientes — Personal Balance

Lista de tareas del proyecto. Copia de la que está en el documento "Personal Balance"
(versión oficial y al día). "Niko" = solo la puede hacer él, en su iPhone o en sus cuentas.

App v76 · web-52.

## Pendiente

- [ ] **Niko** — iPhone: crear el atajo de pagos (con guía de Claude) y compartir el enlace de iCloud
- [ ] iPhone: botones "Instalar atajo" y "Conectar" + guía en la app (cuando haya enlace)
- [ ] **Niko** — Android: app en Google Play que detecta los pagos (dar de alta la cuenta, 25 $)
- [ ] **Niko** — Probar el escáner con la cámara del iPhone (la lectura con la IA ya está comprobada)
- [ ] **Niko** — Regenerar el token Flex de IBKR y pegarlo de nuevo
- [ ] Efecto cristal del menú en el iPhone
- [ ] Más brókeres (módulo avanzado): Trade Republic, Revolut, MyInvestor, Benchmark
- [ ] **Niko** — Día de pago de Aqua Dama
- [ ] "Pro" decidido y comprobado en el servidor (cuando se construya la versión de pago)
- [ ] CSP más estricta con script-src (red extra contra XSS; requiere nonces)
- [ ] Más adelante: conectar el banco (open banking, de pago)
- [ ] Prueba piloto con 10–20 personas
- [ ] **Niko** — Publicar en Google Play y App Store cuando todo esté listo
- [ ] Admin dentro de la app (PWA): dibujar el panel (uso, usuarios, mensajes) de forma nativa dentro de la app, en vez de abrir la web en otra pestaña. Requiere crear endpoints JSON protegidos (Bearer + admin) y rehacer cada vista en la app. De momento la pestaña "Admin" abre el panel web (que se ve igual porque es el mismo).

## Hecho (desde la v50)

- [x] (2026-11-27) Selector de mes: pulsar el nombre del mes abre un menú para saltar a cualquier mes (app y web), sin pasar mes a mes.
- [x] (2026-11-27) Importación automática de facturas (semiautomática): robots semanales (lunes) leen el correo de **Fenie/luz** (del PDF) y **Digi** (del cuerpo) y envían un correo con un enlace de "un toque" que crea/actualiza el gasto fijo tras confirmar. Pilot: solo Niko (se lee su Gmail).
- [x] (2026-11-27) Gastos fijos con **mes de inicio** (`desde`): un gasto fijo puede empezar en su mes de cargo y no aparece ni cuenta en meses anteriores (p. ej. la luz empieza en diciembre).
- [x] (2026-11-27) Enlace de "un toque" genérico `?fijo=Nombre&imp=...&dia=...&mes=...` para cualquier gasto fijo.
- [x] (2026-11-27) Perfil: quitados los iconos de emoji infantiles (avatar = foto o inicial) y añadida la pestaña **Admin** en la barra (como en la web), solo para el administrador.

- [x] (2026-11-25) Panel: permiso de Firebase Authentication (Viewer) para que la cuenta del servidor pueda listar a los usuarios.
- [x] (2026-11-25) Arreglada la lectura del perfil: el panel ya muestra dispositivo, país, idioma y días activos (antes `load_profile` descartaba esos campos al leerlos, aunque sí estaban guardados).
- [x] (2026-11-25) País deducido por **zona horaria** (antes por el idioma, que daba EE. UU. a usuarios en Europa). La web ahora captura la zona horaria; la app ya lo hacía.
- [x] (2026-11) Panel de administración con "Uso de la app": botón Admin el primero de la barra, solo Niko.
- [x] (2026-11) Métricas de uso por usuario: web o app, país, desde cuándo y frecuencia diaria — sin datos económicos de los usuarios.
- [x] (2026-11) Registro de errores con tres botones por error (Analizar con IA, Marcar resuelto, Copiar), aviso al instante y resumen diario.
- [x] (2026-11) Copias de seguridad automáticas de Firestore (PITR + diaria + semanal).
- [x] (2026-11) Política de privacidad y aviso de datos (/privacidad).
- [x] (2026-11) Alerta de gasto en Google Cloud (5 €).
- [x] (2026-11) Historial del año mes a mes en Resumen y "gastado este año" real.
- [x] (2026-11) "Gastos mensuales" incluye el día a día en el total del mes.
- [x] (2026-11) Arreglada la falsa "Cuota vencida" de los préstamos; tick verde "Al día".
- [x] (2026-11) Cola sin conexión del escáner: las fotos sin internet se guardan y se procesan al volver.
- [x] (2026-11-23) Auditoría de seguridad completa (SSRF, XSS, inyección, CSRF, IDOR, subidas, cabeceras): sin vulnerabilidades abiertas.
- [x] (2026-11-23) Foto de perfil: solo imágenes subidas, sin enlaces externos ni SVG.

## Ideas por decidir (plan Pro, aún sin construir)

- Modelo freemium: gratis útil + 10 escaneos/mes; **Pro 1,99 € (pago único)** = todo
  ilimitado (uso justo, con tope oculto anti-abuso). Admin puede regalar Pro, registrado solo para el admin.
- Función "Mis documentos": avisos de caducidad de DNI/pasaporte/carnet (lectura de la
  fecha en el móvil, sin guardar la imagen). Tarjetas de banco: fuera (ya avisa el banco).
- Posible nicho: gestión de vida para personas que viven fuera de su país.
