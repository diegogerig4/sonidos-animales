/* Recoge el audio del micrófono y lo envía en bloques al hilo principal. */
class AudioProcessor extends AudioWorkletProcessor {
  constructor() { super(); this.buf = new Float32Array(2048); this.i = 0; }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) for (let k = 0; k < ch.length; k++) {
      this.buf[this.i++] = ch[k];
      if (this.i >= this.buf.length) { this.port.postMessage(this.buf.slice()); this.i = 0; }
    }
    return true;
  }
}
registerProcessor('audio-processor', AudioProcessor);
