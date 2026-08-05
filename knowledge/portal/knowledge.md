# Portal — knowledge

## The tag web, as it looks when it is right (2026-08-05)

`fcfcde7631a910068f005427d67b30cfbfd732fb` is the state the web was signed off
in: it searches visibly for a couple of seconds, then crawls for ever without
ever coming to a stop. Four rounds of tuning got there, and three of the four
went somewhere worse first, so if it ever "goes mad" again this is the picture
to come back to — restore `src/tglinks/graph.py` from that commit rather than
re-derive the numbers. Every rule behind them is portal R7.1–R7.10.

The whole tuning, in one place. Nothing here is a pixel: `unit` is the room one
bubble has, `Math.max(56, Math.min(room, Math.min(W, H) * 0.62))`, and every
length is a share of it.

| what | value | why that one |
| --- | --- | --- |
| `BUDGET` | 320 frames | the ceiling on the search, not its length. Actually spent: 157 on a laptop, 272 on a phone, 48–132 after a pick |
| `MARK` | 12 frames | the window the layout is compared with itself over. Shorter mistakes the pause at the top of a swing for the end |
| rest test | `far < MARK * 0.5` twice | net movement, not speed: no bubble's speed ever reaches zero |
| damping | `0.8 - 0.3 * min(1, steps / 90)` | fixed damping left a tail that crept on for ever; stiffer forces (springs 0.036, pull 0.018, tug 0.17, damp 0.66) gave a standing oscillation plateauing at 13–17px per window |
| threads | `(d - rest) * 0.02 * k` | soft, `sqrt(deg)`-normalised, or a hub on ten threads is dragged through its neighbours |
| separation | `0.34` | boxes the width of the label, never circles |
| centre pull | `0.011` picked / `0.004` the rest | |
| box tug | `needX/needY * 0.1`, a **force** | as a position scale it skipped the damping and no fixed point existed |
| speed ceiling | `unit * 0.075` searching | nothing bounded the first step and one bubble flung 164px in one frame; the peak is now 33.8 |
| crawl ceiling | `unit * 0.0055` | about a pixel a frame. 20s of crawling: 2400 frames, zero overlaps at 20 samples, 38px of drift, nothing escaped |
| tidy | 12 frames of `unpack(4, 0.5)`, then `unpack(60, 1)` | the leftover overlaps come out across frames; all at once reads as a glitch |

Measured on the real prod graph — 14 nodes, apparel 57 down to home-decor 21,
41 edges — at 1440×900 and 390×844, on load and after three picks each.

### How it was measured

Playwright cannot open `file:`, and a canvas has nothing to assert on, so the
rig serves a standalone page over `http://127.0.0.1:8731` with
`CanvasRenderingContext2D.prototype.arc` and `fillText` patched to push into
`window.SEEN`. Two traps in it, both of which produced confident nonsense:

- Headless rAF throttles between `evaluate` calls, so a probe that waits one
  quiet window samples a mid-animation frame. Four consecutive stable 700ms
  windows is the settle detector that stopped lying.
- Frame-to-frame displacement keyed by draw index is meaningless — the order
  changes. Key it by the label text (`SEEN.words[i].t`).
