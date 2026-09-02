# Kitel STM32F446RE firmware

This is the source-only copy of the hardware-team handoff
`kitel2026final.zip` (SHA-256
`a109ae0a7317b207e91c1b6f8fd960e3d9413074a77e70214b96c1b5b22bc072`). Generated `Debug/`
objects, listings, maps, and the handoff ELF are deliberately excluded so they cannot be mistaken
for firmware built from the current source.

The authoritative device wire contract is:

- `HELLO\n` followed by one host `FRAME` response;
- `NAV,U|D|L|R|N|P,S\n` for one navigation step;
- `NAV,C,S|L\n` for confirm/replay or reading exit;
- `NAV,V,A|R\n` for capture/reading mode;
- one host `FRAME,page,node,span,offset,generation,c0..c9\n` after every command.

Buttons use active-low GPIO inputs with internal pull-ups. Navigation/page holds wait 650 ms and
then repeat SHORT steps every 180 ms. Confirm never repeats; it emits SHORT or LONG once on release.

Open `kitel2026final.ioc` in STM32CubeMX/CubeIDE to inspect or regenerate pin setup. Regeneration must
preserve the labels and pull-ups for PA0, PA1, PA4, PB0, PB1, PC0, PC1, and PC2. A physical build,
flash, header-map review, and GPIO test remain required before hardware acceptance.
