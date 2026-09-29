# AuraLAN visual identity

AuraLAN uses the **Signal Halo** identity: a central node surrounded by radiating signal arcs. The mark represents the product's core job — making the normally invisible local network visible and understandable.

## Core palette

| Token | Hex | Use |
| --- | --- | --- |
| Midnight | `#0B1220` | Dark surfaces, depth, app-icon background |
| Aura Blue | `#3B82F6` | Primary actions, discovery, network state |
| Violet Glow | `#8B5CF6` | Intelligence, secondary emphasis, media devices |
| Signal Mint | `#22D3A7` | Connected/online state, smart-home presence |
| Cloud | `#E5E7EB` | Light contrast and neutral UI |

The UI may use lighter/darker tonal variants for contrast, but new feature colors should derive from these tokens unless they represent a semantic state such as warning or error.

## Logo

The Signal Halo mark must remain simple at small sizes. Do not add text inside the mark, extra nodes, router silhouettes or literal Wi-Fi glyphs. Use `frontend/assets/icons/logo-mark.svg` for the standalone mark and `wordmark.svg` when the name should travel with it.

The favicon and maskable icon use the same geometry on Midnight so the product remains recognizable from browser tab to installed PWA.

## Interface principles

- Dark mode is anchored in Midnight rather than neutral black.
- Primary interactive emphasis is Aura Blue.
- Violet Glow is secondary and should not compete with primary actions.
- Signal Mint means healthy, connected or online.
- Cards use restrained translucent surfaces and very subtle aura gradients.
- Device icons use category colour to improve scanning without turning the list into a rainbow.
- Product/service logos may keep a recognizable product colour where useful, inside AuraLAN-shaped surfaces.
- Glow is an accent. Text, controls and dense information must stay crisp.

## Device colour language

Blue: phones/tablets/watches. Indigo: computers. Violet: TVs/media/consoles/VR. Mint: speakers, smart-home and IoT. Cyan: networking and climate devices. Amber: cameras. Slate: printers/unknown infrastructure. Raspberry Pi may use its recognizable raspberry accent.

## Maintenance

The branding layer is isolated in `frontend/brand-theme.css` and loaded after `app.css`. Functional layout and application behaviour should stay in the existing frontend files. New visual changes should prefer brand tokens and reusable selectors over one-off inline styling.
