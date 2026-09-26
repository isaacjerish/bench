# Benchy demo film

This is the first Remotion cut for the HackGT hardware demo. It is intentionally a short prelude rather than a finished product film:

1. `01 / QUESTION` establishes the problem.
2. `02 / INSTRUMENT` introduces the physical board and probe vocabulary.
3. `03 / EVIDENCE` shows the distinction between a firmware claim and a physical measurement.
4. `PHYSICAL EVIDENCE` is a clean handoff card for real breadboard footage.

The final scene is the edit point. Replace it with a real clip later using `OffthreadVideo` or `Html5Video`; keep the opening three scenes as the designed lead-in. Avoid inventing people, hands, or fake product shots. The visual language is deliberately limited to a dark lab UI, a schematic-like board, measured values, and one green evidence accent.

## Run it

```sh
npm install
npm run studio
npm run render
```

The Remotion APIs used here are `Sequence`, `spring`, `interpolate`, and `TransitionSeries` with a restrained fade. See the official [Transitions guide](https://www.remotion.dev/docs/transitioning) and [API overview](https://www.remotion.dev/docs/api).

## Add physical footage

Put a clip in `public/physical-demo.mp4`, then replace the `PhysicalSlot` body in `src/Scenes.tsx` with:

```tsx
<OffthreadVideo src={staticFile('physical-demo.mp4')} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
```

Keep the clip's first frame visually close to the handoff card: off-white surface, centered board, and a little negative space for the existing lower caption.
