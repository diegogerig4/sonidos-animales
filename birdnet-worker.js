/*
 * Reconocimiento de aves por sonido con BirdNET (Cornell Lab / TU Chemnitz).
 * Adaptado de BirdNET Live (MIT, BirdNET-Team) y georg95/birdnet-web.
 * El modelo BirdNET se usa bajo licencia CC BY-NC-SA 4.0 (uso no comercial).
 */
importScripts('https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@4.14.0/dist/tf.min.js');

const BASE = 'https://cdn.jsdelivr.net/gh/birdnet-team/real-time-pwa@6ab67ac09fa64d98858b90f14318229aca9bb7dc/public/models/birdnet';
const WINDOW = 144000; // 3 s a 48 kHz

let model = null, areaModel = null, birds = [], geo = null;

class MelSpecLayerSimple extends tf.layers.Layer {
  constructor(config) {
    super(config);
    this.sampleRate = config.sampleRate;
    this.specShape = config.specShape;
    this.frameStep = config.frameStep;
    this.frameLength = config.frameLength;
    this.melFilterbank = tf.tensor2d(config.melFilterbank);
  }
  build() {
    this.magScale = this.addWeight('magnitude_scaling', [], 'float32', tf.initializers.constant({ value: 1.23 }));
    super.build();
  }
  computeOutputShape(inputShape) { return [inputShape[0], this.specShape[0], this.specShape[1], 1]; }
  call(inputs) {
    return tf.tidy(() => {
      const x = inputs[0];
      return tf.stack(x.split(x.shape[0]).map(input => {
        let spec = input.squeeze();
        spec = tf.sub(spec, tf.min(spec, -1, true));
        spec = tf.div(spec, tf.max(spec, -1, true).add(1e-6));
        spec = tf.sub(spec, 0.5).mul(2.0);
        spec = tf.engine().runKernel('STFT', { signal: spec, frameLength: this.frameLength, frameStep: this.frameStep });
        spec = tf.matMul(spec, this.melFilterbank).pow(2.0);
        spec = spec.pow(tf.div(1.0, tf.add(1.0, tf.exp(this.magScale.read()))));
        spec = tf.reverse(spec, -1);
        spec = tf.transpose(spec).expandDims(-1);
        return spec;
      }));
    });
  }
  static get className() { return 'MelSpecLayerSimple'; }
}

tf.registerKernel({
  kernelName: 'STFT',
  backendName: 'webgl',
  kernelFunc: ({ backend, inputs: { signal, frameLength, frameStep } }) => {
    const innerDim = frameLength / 2;
    const batch = (signal.size - frameLength + frameStep) / frameStep | 0;
    let cur = backend.runWebGLProgram({
      variableNames: ['x'],
      outputShape: [batch, frameLength],
      userCode: `void main(){
        ivec2 c=getOutputCoords();
        int p=c[1]%${innerDim};
        int k=0;
        for(int i=0;i<${Math.log2(innerDim)};++i){
          if((p & (1<<i))!=0){ k|=(1<<(${Math.log2(innerDim) - 1}-i)); }
        }
        int i=2*k;
        if(c[1]>=${innerDim}){ i=2*(k%${innerDim})+1; }
        int q=c[0]*${frameLength}+i;
        float val=getX((q/${frameLength})*${frameStep}+ q % ${frameLength});
        float cosArg=${2.0 * Math.PI / frameLength}*float(q);
        float mul=0.5-0.5*cos(cosArg);
        setOutput(val*mul);
      }`
    }, [signal], 'float32');
    for (let len = 1; len < innerDim; len *= 2) {
      const prev = cur;
      cur = backend.runWebGLProgram({
        variableNames: ['x'],
        outputShape: [batch, innerDim * 2],
        userCode: `void main(){
          ivec2 c=getOutputCoords();
          int b=c[0];
          int i=c[1];
          int k=i%${innerDim};
          int isHigh=(k%${len * 2})/${len};
          int highSign=(1 - isHigh*2);
          int baseIndex=k - isHigh*${len};
          float t=${Math.PI / len}*float(k%${len});
          float a=cos(t);
          float bsin=sin(-t);
          float oddK_re=getX(b, baseIndex+${len});
          float oddK_im=getX(b, baseIndex+${len + innerDim});
          if(i<${innerDim}){
            float evenK_re=getX(b, baseIndex);
            setOutput(evenK_re + (oddK_re*a - oddK_im*bsin)*float(highSign));
          } else {
            float evenK_im=getX(b, baseIndex+${innerDim});
            setOutput(evenK_im + (oddK_re*bsin + oddK_im*a)*float(highSign));
          }
        }`
      }, [prev], 'float32');
      backend.disposeIntermediateTensorInfo(prev);
    }
    const real = backend.runWebGLProgram({
      variableNames: ['x'],
      outputShape: [batch, innerDim + 1],
      userCode: `void main(){
        ivec2 c=getOutputCoords();
        int b=c[0];
        int i=c[1];
        int zI=i%${innerDim};
        int conjI=(${innerDim}-i)%${innerDim};
        float Zk0=getX(b,zI);
        float Zk1=getX(b,zI+${innerDim});
        float Zk_conj0=getX(b,conjI);
        float Zk_conj1=-getX(b,conjI+${innerDim});
        float t=${-2.0 * Math.PI}*float(i)/float(${innerDim * 2});
        float diff0=Zk0 - Zk_conj0;
        float diff1=Zk1 - Zk_conj1;
        float result=(Zk0+Zk_conj0 + cos(t)*diff1 + sin(t)*diff0)*0.5;
        setOutput(result);
      }`
    }, [cur], 'float32');
    backend.disposeIntermediateTensorInfo(cur);
    return real;
  }
});

async function init() {
  try {
    const ok = await tf.setBackend('webgl');
    if (!ok) throw new Error('webgl');
  } catch (e) {
    postMessage({ message: 'error', error: 'webgl' });
    return;
  }
  try {
    tf.serialization.registerClass(MelSpecLayerSimple);
    model = await tf.loadLayersModel(BASE + '/model.json', {
      onProgress: p => postMessage({ message: 'progress', progress: Math.round(p * 85) })
    });
    postMessage({ message: 'progress', progress: 88 });
    tf.tidy(() => { model.predict(tf.zeros([1, WINDOW])); });
    postMessage({ message: 'progress', progress: 93 });
    try { areaModel = await tf.loadGraphModel(BASE + '/area-model/model.json'); } catch (e) { areaModel = null; }
    postMessage({ message: 'progress', progress: 97 });
    const en = (await fetch(BASE + '/labels/en_us.txt').then(r => r.text())).split('\n');
    let es = en;
    try { es = (await fetch(BASE + '/labels/es.txt').then(r => r.text())).split('\n'); } catch (e) {}
    birds = en.map((line, i) => {
      const [sci, com] = line.replace('\r', '').split('_');
      const [, comEs] = (es[i] || line).replace('\r', '').split('_');
      return { sci: sci || line, common: comEs || com || sci, isSpecies: !!sci && !!com && sci !== com, geo: 1 };
    });
    postMessage({ message: 'ready', hasGeo: !!areaModel });
  } catch (e) {
    postMessage({ message: 'error', error: 'load', detail: String(e) });
  }
}
init();

onmessage = async ({ data }) => {
  if (data.message === 'geo' && areaModel && birds.length) {
    const start = new Date(new Date().getFullYear(), 0, 1);
    const week = Math.min(48, Math.max(1, Math.ceil((Date.now() - start) / 604800000 * 48 / 52)));
    const scores = tf.tidy(() => areaModel.predict(tf.tensor([[data.latitude, data.longitude, week]])).dataSync());
    for (let i = 0; i < birds.length; i++) birds[i].geo = scores[i];
    geo = true;
    postMessage({ message: 'geo-ready' });
  }
  if (data.message === 'predict' && model) {
    const input = tf.tensor2d(data.pcm, [1, WINDOW]);
    const out = model.predict(input);
    const probs = await out.data();
    input.dispose(); out.dispose();
    const res = [];
    for (let i = 0; i < probs.length; i++) {
      const b = birds[i];
      if (!b || !b.isSpecies || probs[i] < data.threshold) continue;
      if (geo && b.geo < 0.02) continue;
      res.push({ sci: b.sci, common: b.common, conf: probs[i] });
    }
    res.sort((a, b) => b.conf - a.conf);
    postMessage({ message: 'result', results: res.slice(0, 5) });
  }
};
