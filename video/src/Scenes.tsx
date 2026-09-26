import React from 'react';
import {
  AbsoluteFill,
  Easing,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {linearTiming, pushCut, TransitionSeries} from '@remotion/transitions';

const ink = '#f3f0e9';
const paper = '#111210';
const muted = '#8d918a';
const green = '#b7f397';
const line = '#30332f';

const FadeIn: React.FC<{children: React.ReactNode; delay?: number; y?: number}> = ({children, delay = 0, y = 18}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame - delay, [0, 18], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const translate = interpolate(frame - delay, [0, 24], [y, 0], {easing: Easing.out(Easing.cubic), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return <div style={{opacity, transform: `translateY(${translate}px)`}}>{children}</div>;
};

const Grid: React.FC = () => <div style={{position: 'absolute', inset: 0, opacity: .12, backgroundImage: 'linear-gradient(#777 1px, transparent 1px), linear-gradient(90deg, #777 1px, transparent 1px)', backgroundSize: '72px 72px'}} />;

const Header: React.FC<{section: string}> = ({section}) => <div style={{position: 'absolute', top: 54, left: 68, right: 68, display: 'flex', justifyContent: 'space-between', color: muted, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 18, letterSpacing: 2}}><span>BENCHY / LAB INSTRUMENT</span><span>{section}</span></div>;

const BenchUnit: React.FC = () => <div style={{width: 790, height: 430, position: 'relative', filter: 'drop-shadow(0 32px 42px #000a)'}}>
  <div style={{position: 'absolute', left: 36, top: 62, width: 660, height: 312, borderRadius: 22, background: '#20231f', border: `1px solid #464b43`, transform: 'skewY(-4deg)'}} />
  <div style={{position: 'absolute', left: 72, top: 28, width: 660, height: 312, borderRadius: 22, background: '#171a17', border: `1px solid #50564d`}} />
  <div style={{position: 'absolute', left: 104, top: 62, width: 570, height: 220, borderRadius: 12, background: '#101210', border: `1px solid ${line}`}} />
  <div style={{position: 'absolute', left: 128, top: 85, color: muted, font: '15px ui-monospace, monospace', letterSpacing: 1}}>BENCHY // ACTIVE PROBE MAP</div>
  <div style={{position: 'absolute', left: 128, top: 126, width: 510, height: 1, background: line}} />
  <div style={{position: 'absolute', left: 128, top: 154, display: 'flex', gap: 34, color: ink, font: '20px ui-monospace, monospace'}}><span><b style={{color: green}}>P1</b> 2.548 V</span><span><b style={{color: green}}>P2</b> 3.220 V</span></div>
  <div style={{position: 'absolute', left: 128, top: 202, color: '#d4d8d0', font: '17px ui-monospace, monospace'}}>BUS  SDA 0 edges   SCL 241 edges</div>
  <div style={{position: 'absolute', left: 128, top: 243, color: '#f0ca79', font: '17px ui-monospace, monospace'}}>STATUS  investigating</div>
  <div style={{position: 'absolute', right: 64, bottom: 44, color: muted, font: '15px ui-monospace, monospace'}}>S3 LAB CONTROLLER</div>
  <div style={{position: 'absolute', left: 95, bottom: 20, width: 18, height: 7, borderRadius: 4, background: green, boxShadow: `0 0 18px ${green}`}} />
</div>;

const EvidencePanel: React.FC = () => <div style={{width: 730, border: `1px solid ${line}`, borderRadius: 16, background: '#0b0c0b', padding: 30, color: '#c8cdc3', boxShadow: '0 24px 70px #0009'}}><div style={{display: 'flex', justifyContent: 'space-between', font: '15px ui-monospace, monospace', color: muted, letterSpacing: 1}}><span>RUN 0007 / IMU_LINK</span><span>LIVE CAPTURE</span></div><div style={{marginTop: 22, display: 'grid', gridTemplateColumns: '130px 1fr 120px', rowGap: 16, font: '18px ui-monospace, monospace'}}><span style={{color: muted}}>14:23:04</span><span>WHO_AM_I 0x70</span><b style={{color: green, textAlign: 'right'}}>observed</b><span style={{color: muted}}>14:23:05</span><span>P2 / MPU_VCC 3.220 V</span><b style={{color: green, textAlign: 'right'}}>in range</b><span style={{color: muted}}>14:23:06</span><span>SCL transitions 241</span><b style={{color: green, textAlign: 'right'}}>active</b><span style={{color: muted}}>14:23:06</span><span>SDA transitions 0</span><b style={{color: '#f0ca79', textAlign: 'right'}}>check path</b></div><div style={{marginTop: 28, paddingTop: 22, borderTop: `1px solid ${line}`, display: 'flex', gap: 18, alignItems: 'center'}}><div style={{width: 10, height: 10, borderRadius: '50%', background: '#f0ca79'}} /><div><div style={{font: '17px ui-sans-serif, system-ui, sans-serif', color: ink}}>Next discriminating test</div><div style={{marginTop: 5, font: '16px ui-monospace, monospace', color: muted}}>isolate the SDA sense branch, then repeat capture</div></div></div></div>;

const Intro: React.FC = () => <AbsoluteFill style={{background: paper, color: ink}}><Grid /><Header section="01 / QUESTION" /><div style={{position: 'absolute', left: 110, top: 270, maxWidth: 1100}}><FadeIn><div style={{font: '700 116px/0.96 ui-sans-serif, system-ui, sans-serif', letterSpacing: -5}}>When a circuit<br />misbehaves, <span style={{color: green}}>measure.</span></div></FadeIn><FadeIn delay={15}><div style={{marginTop: 50, color: muted, font: '24px/1.45 ui-sans-serif, system-ui, sans-serif', maxWidth: 580}}>Benchy turns an unknown breadboard into a sequence of testable questions.</div></FadeIn></div><div style={{position: 'absolute', right: 120, bottom: 120, color: muted, font: '16px ui-monospace, monospace'}}>HACKGT 13 / HARDWARE</div></AbsoluteFill>;

const Instrument: React.FC = () => { const frame = useCurrentFrame(); const scale = spring({fps: 30, frame: frame - 12, config: {damping: 200}}); return <AbsoluteFill style={{background: paper, color: ink}}><Grid /><Header section="02 / INSTRUMENT" /><div style={{position: 'absolute', left: 110, top: 180}}><FadeIn><div style={{font: '700 32px ui-sans-serif, system-ui, sans-serif', color: muted}}>THE BOARD STAYS REAL.</div></FadeIn><FadeIn delay={18}><div style={{font: '700 72px/1.05 ui-sans-serif, system-ui, sans-serif', marginTop: 24, letterSpacing: -3}}>The questions<br />become signals.</div></FadeIn><FadeIn delay={42}><div style={{marginTop: 40, color: muted, font: '20px/1.5 ui-sans-serif, system-ui, sans-serif', width: 470}}>Every readout carries its source: an analog probe, a digital edge counter, or the DUT’s own serial claim.</div></FadeIn></div><div style={{position: 'absolute', right: 72, top: 248, transform: `scale(${scale})`, transformOrigin: 'center'}}><BenchUnit /></div><div style={{position: 'absolute', left: 110, bottom: 112, display: 'flex', gap: 62, color: muted, font: '17px ui-monospace, monospace'}}><span><b style={{color: green}}>P1</b> voltage</span><span><b style={{color: green}}>P2</b> rail check</span><span><b style={{color: green}}>BUS</b> edge capture</span></div></AbsoluteFill>; };

const Evidence: React.FC = () => <AbsoluteFill style={{background: paper, color: ink}}><Grid /><Header section="03 / EVIDENCE" /><div style={{position: 'absolute', left: 110, top: 190}}><FadeIn><div style={{font: '700 76px/1.02 ui-sans-serif, system-ui, sans-serif', letterSpacing: -3}}>Read the claim.<br />then test it.</div></FadeIn><FadeIn delay={22}><div style={{marginTop: 38, color: muted, font: '22px/1.4 ui-sans-serif, system-ui, sans-serif', width: 470}}>Benchy keeps the DUT’s report beside independent measurements, so a plausible log can still be challenged.</div></FadeIn><FadeIn delay={52}><div style={{marginTop: 42, display: 'flex', gap: 12, font: '15px ui-monospace, monospace', color: muted}}><span style={{border: `1px solid ${green}`, color: green, padding: '9px 12px'}}>OBSERVED</span><span style={{border: `1px solid #555b53`, padding: '9px 12px'}}>INFERRED</span></div></FadeIn></div><div style={{position: 'absolute', right: 76, top: 182}}><FadeIn delay={14}><EvidencePanel /></FadeIn></div><div style={{position: 'absolute', left: 110, bottom: 102, borderLeft: `2px solid ${green}`, paddingLeft: 18, color: green, font: '18px ui-monospace, monospace'}}>MEASURE → HYPOTHESIZE → TEST</div></AbsoluteFill>;

const PhysicalSlot: React.FC = () => { const frame = useCurrentFrame(); const p = interpolate(frame, [0, 24], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}); return <AbsoluteFill style={{background: '#e9e5dc', color: '#171915'}}><div style={{position: 'absolute', inset: 0, opacity: .28, backgroundImage: 'linear-gradient(90deg, #00000010 1px, transparent 1px)', backgroundSize: '8px 8px'}} /><div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', opacity: p}}><div style={{font: '700 80px/1 ui-sans-serif, system-ui, sans-serif', letterSpacing: -4}}>NOW, SHOW THE BOARD.</div><div style={{marginTop: 30, font: '20px ui-monospace, monospace', color: '#555a52'}}>INSERT PHYSICAL DEMO FOOTAGE HERE</div><div style={{marginTop: 70, width: 840, height: 6, background: '#171915'}}><div style={{width: '32%', height: '100%', background: green}} /></div></div><div style={{position: 'absolute', bottom: 56, left: 68, right: 68, display: 'flex', justifyContent: 'space-between', font: '16px ui-monospace, monospace', color: '#656a62'}}><span>BENCHY / LIVE HARDWARE</span><span>00:09 — PHYSICAL EVIDENCE</span></div></AbsoluteFill>; };

export const BenchyDemo: React.FC = () => <AbsoluteFill style={{fontFamily: 'ui-sans-serif, system-ui, sans-serif'}}><TransitionSeries><TransitionSeries.Sequence durationInFrames={135}><Intro /></TransitionSeries.Sequence><TransitionSeries.Transition presentation={pushCut()} timing={linearTiming({durationInFrames: 12})} /><TransitionSeries.Sequence durationInFrames={150}><Instrument /></TransitionSeries.Sequence><TransitionSeries.Transition presentation={pushCut()} timing={linearTiming({durationInFrames: 12})} /><TransitionSeries.Sequence durationInFrames={180}><Evidence /></TransitionSeries.Sequence><TransitionSeries.Transition presentation={pushCut()} timing={linearTiming({durationInFrames: 12})} /><TransitionSeries.Sequence durationInFrames={135}><PhysicalSlot /></TransitionSeries.Sequence></TransitionSeries></AbsoluteFill>;
