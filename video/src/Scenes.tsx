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

const Breadboard: React.FC = () => <div style={{width: 760, height: 410, border: `1px solid ${line}`, background: '#181b18', borderRadius: 18, position: 'relative', boxShadow: '0 26px 80px #0008'}}>
  <div style={{position: 'absolute', inset: 32, border: `1px solid ${line}`, borderRadius: 10}} />
  {[0,1,2,3,4,5,6,7,8,9,10,11].map((x) => <React.Fragment key={x}>{[0,1].map((y) => <div key={y} style={{position: 'absolute', left: 80 + x * 52, top: 88 + y * 148, width: 7, height: 7, borderRadius: '50%', background: x === 8 && y === 0 ? green : '#666b63'}} />)}</React.Fragment>)}
  <div style={{position: 'absolute', left: 140, top: 168, width: 460, height: 2, background: '#b7f39788', transform: 'rotate(-5deg)', transformOrigin: 'left'}} />
  <div style={{position: 'absolute', left: 300, top: 124, width: 160, height: 98, border: `2px solid ${green}`, borderRadius: 8, opacity: .85}} />
  <div style={{position: 'absolute', right: 52, bottom: 52, color: muted, font: '16px ui-monospace, monospace'}}>DUT / ESP32-C6</div>
</div>;

const Terminal: React.FC = () => <div style={{width: 660, border: `1px solid ${line}`, borderRadius: 12, background: '#0b0c0b', padding: 28, font: '18px/1.75 ui-monospace, SFMono-Regular, Menlo, monospace', color: '#c8cdc3', boxShadow: '0 22px 60px #0009'}}><div style={{color: muted, marginBottom: 12}}>serial / 115200 baud</div><div><b style={{color: green}}>OK</b> IMU_FOUND addr=0x68 who_am_i=0x70</div><div><b style={{color: green}}>OK</b> P2 MPU_VCC 3.227 V</div><div><b style={{color: '#f0ca79'}}>WARN</b> SDA transitions 0 / SCL transitions 241</div><div style={{color: muted}}>hypothesis: SDA contact or pull-up path</div></div>;

const Intro: React.FC = () => <AbsoluteFill style={{background: paper, color: ink}}><Grid /><Header section="01 / QUESTION" /><div style={{position: 'absolute', left: 110, top: 270, maxWidth: 1100}}><FadeIn><div style={{font: '700 116px/0.96 ui-sans-serif, system-ui, sans-serif', letterSpacing: -5}}>When a circuit<br />misbehaves, <span style={{color: green}}>measure.</span></div></FadeIn><FadeIn delay={15}><div style={{marginTop: 50, color: muted, font: '24px/1.45 ui-sans-serif, system-ui, sans-serif', maxWidth: 580}}>Benchy turns an unknown breadboard into a sequence of testable questions.</div></FadeIn></div><div style={{position: 'absolute', right: 120, bottom: 120, color: muted, font: '16px ui-monospace, monospace'}}>HACKGT 13 / HARDWARE</div></AbsoluteFill>;

const Instrument: React.FC = () => { const frame = useCurrentFrame(); const scale = spring({fps: 30, frame: frame - 8, config: {damping: 200}}); return <AbsoluteFill style={{background: paper, color: ink}}><Grid /><Header section="02 / INSTRUMENT" /><div style={{position: 'absolute', left: 110, top: 180}}><FadeIn><div style={{font: '700 32px ui-sans-serif, system-ui, sans-serif', color: muted}}>THE BOARD STAYS REAL.</div></FadeIn><FadeIn delay={10}><div style={{font: '700 72px/1.05 ui-sans-serif, system-ui, sans-serif', marginTop: 24, letterSpacing: -3}}>The questions<br />become signals.</div></FadeIn></div><div style={{position: 'absolute', right: 100, top: 250, transform: `scale(${scale})`, transformOrigin: 'center'}}><Breadboard /></div><div style={{position: 'absolute', left: 110, bottom: 112, display: 'flex', gap: 18, color: muted, font: '17px ui-monospace, monospace'}}><span style={{color: green}}>P1</span> voltage</div><div style={{position: 'absolute', left: 270, bottom: 112, display: 'flex', gap: 18, color: muted, font: '17px ui-monospace, monospace'}}><span style={{color: green}}>P2</span> rail check</div><div style={{position: 'absolute', left: 470, bottom: 112, display: 'flex', gap: 18, color: muted, font: '17px ui-monospace, monospace'}}><span style={{color: green}}>BUS</span> activity</div></AbsoluteFill>; };

const Evidence: React.FC = () => <AbsoluteFill style={{background: paper, color: ink}}><Grid /><Header section="03 / EVIDENCE" /><div style={{position: 'absolute', left: 110, top: 190}}><FadeIn><div style={{font: '700 76px/1.02 ui-sans-serif, system-ui, sans-serif', letterSpacing: -3}}>A serial log<br />is a clue.</div></FadeIn><FadeIn delay={12}><div style={{marginTop: 38, color: muted, font: '22px/1.4 ui-sans-serif, system-ui, sans-serif', width: 480}}>A physical reading is what lets the agent separate firmware claims from the circuit underneath.</div></FadeIn></div><div style={{position: 'absolute', right: 110, top: 190}}><FadeIn delay={8}><Terminal /></FadeIn></div><div style={{position: 'absolute', left: 110, bottom: 102, borderLeft: `2px solid ${green}`, paddingLeft: 18, color: green, font: '18px ui-monospace, monospace'}}>MEASURE → HYPOTHESIZE → TEST</div></AbsoluteFill>;

const PhysicalSlot: React.FC = () => { const frame = useCurrentFrame(); const p = interpolate(frame, [0, 24], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}); return <AbsoluteFill style={{background: '#e9e5dc', color: '#171915'}}><div style={{position: 'absolute', inset: 0, opacity: .28, backgroundImage: 'linear-gradient(90deg, #00000010 1px, transparent 1px)', backgroundSize: '8px 8px'}} /><div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', opacity: p}}><div style={{font: '700 80px/1 ui-sans-serif, system-ui, sans-serif', letterSpacing: -4}}>NOW, SHOW THE BOARD.</div><div style={{marginTop: 30, font: '20px ui-monospace, monospace', color: '#555a52'}}>INSERT PHYSICAL DEMO FOOTAGE HERE</div><div style={{marginTop: 70, width: 840, height: 6, background: '#171915'}}><div style={{width: '32%', height: '100%', background: green}} /></div></div><div style={{position: 'absolute', bottom: 56, left: 68, right: 68, display: 'flex', justifyContent: 'space-between', font: '16px ui-monospace, monospace', color: '#656a62'}}><span>BENCHY / LIVE HARDWARE</span><span>00:09 — PHYSICAL EVIDENCE</span></div></AbsoluteFill>; };

export const BenchyDemo: React.FC = () => <AbsoluteFill style={{fontFamily: 'ui-sans-serif, system-ui, sans-serif'}}><TransitionSeries><TransitionSeries.Sequence durationInFrames={90}><Intro /></TransitionSeries.Sequence><TransitionSeries.Transition presentation={pushCut()} timing={linearTiming({durationInFrames: 12})} /><TransitionSeries.Sequence durationInFrames={105}><Instrument /></TransitionSeries.Sequence><TransitionSeries.Transition presentation={pushCut()} timing={linearTiming({durationInFrames: 12})} /><TransitionSeries.Sequence durationInFrames={105}><Evidence /></TransitionSeries.Sequence><TransitionSeries.Transition presentation={pushCut()} timing={linearTiming({durationInFrames: 12})} /><TransitionSeries.Sequence durationInFrames={84}><PhysicalSlot /></TransitionSeries.Sequence></TransitionSeries></AbsoluteFill>;
