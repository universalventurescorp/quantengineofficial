# The Quiet Ledger: identidad del canal

Los archivos listos para subir están en `out/`. Para regenerarlos (por ejemplo, después de cambiar un color):

```bash
python branding/make_branding.py
```

| Archivo | Dónde va en YouTube Studio › Personalización |
|---|---|
| `out/profile_800.png` | **Foto de perfil** (manual: la API de YouTube no permite cambiarla) |
| `out/banner_2560x1440.png` | **Banner**. Lo sube el sistema solo en la primera corrida |
| `out/watermark_150.png` | **Marca de agua** → mostrar durante todo el video (manual) |

Paleta: negro cálido `#0D0C0B`, pergamino `#ECE4D4`, oro viejo `#CDA660`.
Tipografías: **Cormorant Garamond** y **Jost**, ambas con licencia SIL Open Font License (copias en `fonts/`).
