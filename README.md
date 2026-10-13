# The Quiet Ledger: canal de YouTube automatizado

The Quiet Ledger publica documentales largos (unos 80 minutos), calmados y cinematográficos sobre la historia del dinero: monedas e imperios, banqueros y burbujas, el oro, la inflación y las ideas que construyeron la economía moderna. Están pensados para aprender, relajarse y dormir. Cada episodio sale con 3 Shorts verticales, que se publican uno por día.

Todo el proceso es automático y usa solo herramientas gratuitas: tema, guion, revisión de datos, voz, imágenes de museos, gráficos con datos reales, música original, edición, miniaturas, Shorts, control de calidad, subida y seguimiento de resultados.

## Por qué este formato

| Criterio | Por qué funciona |
|---|---|
| Retención | El contenido largo para dormir es el que más horas de visualización genera. Es el camino más corto a las horas que pide el Programa de Socios (8.000 horas desde febrero de 2027). |
| Imagen | Monedas, cuadros y grabados de museos con licencia libre (The Met, Art Institute of Chicago, Wikimedia Commons), más gráficos de datos reales que se dibujan lentamente. Opcionalmente, tomas filmadas por el estudio. |
| Credibilidad | Las cifras salen de FRED (Reserva Federal de St. Louis) y del Banco Mundial. El guion solo puede citar los números que el sistema descargó, y una segunda revisión de Claude corrige errores. |
| Diferencia | "Historia para dormir" está lleno de canales con imágenes generadas por IA. "Economía para dormir" con imagen de museo y datos reales casi no existe. |

## Qué hace en cada episodio

```
Tema (cola que se rellena sola y aprende de los videos que mejor funcionan)
 └─ Claude: esquema → elige qué datos graficar → capítulos con cifras reales → gancho inicial → revisión de datos
     └─ Kokoro TTS (open source): narración pausada + subtítulos sincronizados
         └─ Imágenes: museos y archivos de dominio público / CC0 (monedas, cuadros, grabados, fotos históricas)
         └─ Gráficos: series reales de FRED / Banco Mundial que se dibujan solas
         └─ (Opcional) tomas del estudio desde una carpeta de Google Drive
             └─ Música original (pads cálidos + piano suave, generada por código, sin derechos)
                 └─ Edición: movimientos de cámara suaves, fundidos, polvo cálido a la luz de una vela, acabado de cine
                     └─ 3 miniaturas · 3 Shorts · control de calidad
                         └─ YouTube: episodio a las 18:00 de Nueva York + un Short por día + informe de resultados
```

## Calendario automático

- El workflow corre **todos los días a las 09:07 de Lima**.
- Produce un episodio los días de `schedule.episode_days` en `config.yaml` (por defecto lunes, miércoles y viernes). Los demás días no hace nada.
- El episodio queda **programado a las 23:00 UTC** (18:00 en Nueva York). Si la producción termina después de esa hora, se publica al terminar.
- Los Shorts quedan programados **uno por día a las 16:00 UTC** (11:00 en Lima).
- Para subir a un episodio diario, pon los 7 días en `episode_days`.

## Configuración (una sola vez, unos 15 minutos)

1. **Apagar el bot viejo:** en el repo `quantengine-auto` → **Actions** → workflow diario → **⋯ → Disable workflow**.
2. **Canal (YouTube Studio → Personalización → Perfil):**
   - Nombre: `The Quiet Ledger`. Handle: `@thequietledgerdocs`.
   - Foto: `branding/out/profile_800.png`.
   - Marca de agua (Personalización → Marca): `branding/out/watermark_150.png`.
   - El banner, la descripción y las palabras clave los pone el sistema solo en la primera corrida.
3. **Google Cloud** (el mismo proyecto que ya usa QuantEngine): en *APIs y servicios → Biblioteca*, habilita **YouTube Analytics API**. La YouTube Data API ya está habilitada.
4. **Token de YouTube**, en tu computadora, con el `client_secret.json` de ese proyecto:
   ```
   pip install google-auth-oauthlib
   python scripts/get_youtube_token.py client_secret.json
   ```
   Entra con la cuenta dueña del canal y elige el canal. Si Google muestra "app no verificada", pulsa *Configuración avanzada → Ir a…*. Copia los 3 valores que imprime.
5. **Token de Claude**, en tu computadora: `claude setup-token`. Copia el token.
6. **Secretos en GitHub** (este repo → *Settings → Secrets and variables → Actions → New repository secret*):

   | Nombre | Valor |
   |---|---|
   | `CLAUDE_CODE_OAUTH_TOKEN` | el token de Claude |
   | `YT_CLIENT_ID` | del paso 4 |
   | `YT_CLIENT_SECRET` | del paso 4 |
   | `YT_REFRESH_TOKEN` | del paso 4 |
   | `FRED_API_KEY` | opcional. Sin él, FRED funciona igual |

7. **Primera corrida:** *Actions → produce-episode → Run workflow*. Tarda unas 3 a 4 horas.

## Dónde ver los resultados

En *Actions*, abre la corrida del día. Abajo, en **Artifacts → episode-files**, están:
- una vista previa de 10 minutos,
- los Shorts,
- las 3 miniaturas,
- el guion,
- el informe de calidad (`qa.json`).

Si el control de calidad falla, **no se sube nada** y el motivo queda en `qa.json`.

`data/analytics.json` guarda las visitas por día y los minutos vistos de cada video. El generador de temas lo usa para inclinarse hacia lo que funciona.

## Cosas que se pueden ajustar en `config.yaml`

| Clave | Qué cambia |
|---|---|
| `schedule.episode_days` | Días en que se produce un episodio |
| `video.target_minutes` | Duración de cada episodio |
| `voice.id` | Voz de Kokoro (`af_bella`, `af_heart`, `bf_emma`...) |
| `shorts.count` | Cuántos Shorts salen de cada episodio |
| `upload.publish_hour_utc` | Hora de publicación del episodio |
| `studio_footage.drive_folder_id` | Carpeta de Drive con tomas del estudio (opcional) |

## Tomas del estudio (opcional)

Si algún día quieren subir la calidad con material propio:
1. Dejen los clips en una carpeta privada de Google Drive. El **nombre del archivo** sirve de etiquetas, por ejemplo `gold-coins-macro-slowmo.mp4`.
2. Pongan el ID de la carpeta en `studio_footage.drive_folder_id`.
3. Generen el token con `--with-drive`.

El sistema elige los clips que encajan con cada capítulo. Sin carpeta, funciona igual.

## Límites conocidos

- **Render:** las máquinas gratuitas de GitHub renderizan en 1080p y aguantan unos 80–90 minutos por episodio. Para 4K o episodios de 2 horas hace falta un equipo propio como runner: creen la variable de repositorio `RUNNER` con valor `self-hosted`.
- **Claude:** comparte el uso del plan Pro con Quiet Cosmos. Si se alcanza el límite, la corrida falla sin subir nada y el tema se reintenta en el siguiente día de episodio.
- **Cuota de YouTube:** un episodio, 3 Shorts y la miniatura caben en la cuota diaria gratuita.
