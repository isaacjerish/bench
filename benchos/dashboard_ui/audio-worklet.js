class BenchyPcmCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunk = new Int16Array(2400); // 100 ms at 24 kHz.
    this.offset = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i += 1) {
      const sample = Math.max(-1, Math.min(1, channel[i]));
      this.chunk[this.offset++] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
      if (this.offset === this.chunk.length) {
        const ready = this.chunk;
        this.chunk = new Int16Array(2400);
        this.offset = 0;
        this.port.postMessage(ready.buffer, [ready.buffer]);
      }
    }
    return true;
  }
}

registerProcessor('benchy-pcm-capture', BenchyPcmCapture);
