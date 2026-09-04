# Kitel STM32F446RE firmware

This is the source-only copy of the hardware-team handoff
`kitel2026final.zip` (SHA-256
`a109ae0a7317b207e91c1b6f8fd960e3d9413074a77e70214b96c1b5b22bc072`). Generated `Debug/`
objects, listings, maps, and the handoff ELF are deliberately excluded so they cannot be mistaken
for firmware built from the current source.

The authoritative device wire contract is version 3:

- STM first sends `HELLO,3\n`; the host immediately returns `ACK,HELLO,3\n`;
- a debounced DOWN press sends `NAV,D,A,<sequence>\n` and release sends
  `NAV,D,R,<sequence>\n` exactly once;
- the host owns DOWN repeat timing, so v3 firmware never queues repeated DOWN
  SHORT commands;
- release therefore cancels future repeat generation without draining an STM
  repeat backlog.

The remaining transport behavior is shared with version 2:

- STM sends `HELLO,2\n`; the host immediately returns `ACK,HELLO,2\n`;
- STM sends `NAV,U|D|L|R|N|P,S,<sequence>\n` for one navigation step;
- STM sends `NAV,C,S|L,<sequence>\n` for confirm/replay or reading exit;
- STM sends `NAV,V,A|R,<sequence>\n` for capture/reading mode;
- the host immediately returns `ACK,<sequence>\n` after accepting a valid command;
- a duplicate sequence is ACKed again but is not applied twice;
- a saturated host input queue returns `NACK,<sequence>,BUSY\n` instead of a false ACK;
- `FRAME,page,node,span,offset,generation,c0..c9\n` is independent of ACK and is
  pushed when the reading presentation changes.

The firmware retries one in-flight versioned command with the same sequence and keeps
polling GPIO while waiting for ACK. During migration it falls back to the legacy
`HELLO,2\n` contract (where DOWN still repeats SHORT in firmware), then to the
three-field `HELLO\n`/blocking `FRAME` contract. The Laptop host supports all
three versions during migration.

Buttons use active-low GPIO inputs with internal pull-ups. In v3 DOWN emits only
press/release edges; other navigation buttons retain firmware repeat. In v2 and
legacy mode navigation/page holds wait 650 ms and repeat SHORT every 180 ms.
Confirm never repeats; it emits SHORT or LONG once on release.

Open `kitel2026final.ioc` in STM32CubeMX/CubeIDE to inspect or regenerate pin setup. Regeneration must
preserve the labels and pull-ups for PA0, PA1, PA4, PB0, PB1, PC0, PC1, and PC2. A physical build,
flash, header-map review, and GPIO test remain required before hardware acceptance.
