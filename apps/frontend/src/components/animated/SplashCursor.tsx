import { useEffect, useRef, type ReactElement } from 'react'

interface SplashCursorProps {
  SIM_RESOLUTION?: number
  DYE_RESOLUTION?: number
  DENSITY_DISSIPATION?: number
  VELOCITY_DISSIPATION?: number
  PRESSURE?: number
  PRESSURE_ITERATIONS?: number
  CURL?: number
  SPLAT_RADIUS?: number
  SPLAT_FORCE?: number
  SHADING?: boolean
  COLOR_UPDATE_SPEED?: number
  BACK_COLOR?: { r: number; g: number; b: number }
  TRANSPARENT?: boolean
  RAINBOW_MODE?: boolean
  COLOR?: string
}

interface PointerData {
  id: number
  texcoordX: number
  texcoordY: number
  prevTexcoordX: number
  prevTexcoordY: number
  deltaX: number
  deltaY: number
  down: boolean
  moved: boolean
  color: { r: number; g: number; b: number }
}

type WebGLAny = WebGL2RenderingContext | WebGLRenderingContext

function createPointer(): PointerData {
  return {
    id: -1, texcoordX: 0, texcoordY: 0,
    prevTexcoordX: 0, prevTexcoordY: 0,
    deltaX: 0, deltaY: 0,
    down: false, moved: false,
    color: { r: 0, g: 0, b: 0 },
  }
}

export function SplashCursor({
  SIM_RESOLUTION = 128,
  DYE_RESOLUTION = 1440,
  DENSITY_DISSIPATION = 5.5,
  VELOCITY_DISSIPATION = 2,
  PRESSURE = 0.1,
  PRESSURE_ITERATIONS = 20,
  CURL = 3,
  SPLAT_RADIUS = 0.2,
  SPLAT_FORCE = 6000,
  SHADING = true,
  COLOR_UPDATE_SPEED = 10,
  BACK_COLOR = { r: 0, g: 0, b: 0 },
  TRANSPARENT = true,
  RAINBOW_MODE = true,
  COLOR = '#c09c2b',
}: SplashCursorProps): ReactElement {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const rafRef = useRef<number>(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    let isActive = true

    const config = {
      SIM_RESOLUTION, DYE_RESOLUTION,
      DENSITY_DISSIPATION, VELOCITY_DISSIPATION,
      PRESSURE, PRESSURE_ITERATIONS,
      CURL, SPLAT_RADIUS, SPLAT_FORCE,
      SHADING, COLOR_UPDATE_SPEED,
      PAUSED: false, BACK_COLOR, TRANSPARENT, RAINBOW_MODE,
    }

    const pointers: PointerData[] = [createPointer()]

    // ── WebGL setup ──────────────────────────────────────────
    function getWebGLContext(c: HTMLCanvasElement) {
      const params = { alpha: true, depth: false, stencil: false, antialias: false, preserveDrawingBuffer: false }
      let gl = c.getContext('webgl2', params) as WebGL2RenderingContext | null
      const isWebGL2 = !!gl
      if (!isWebGL2)
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        gl = (c.getContext('webgl', params) || c.getContext('experimental-webgl', params)) as any

      const glCtx = gl as WebGLAny
      let halfFloat: { HALF_FLOAT_OES: number } | null = null
      let supportLinearFiltering: unknown = null

      if (isWebGL2) {
        glCtx.getExtension('EXT_color_buffer_float')
        supportLinearFiltering = glCtx.getExtension('OES_texture_float_linear')
      } else {
        halfFloat = glCtx.getExtension('OES_texture_half_float') as { HALF_FLOAT_OES: number } | null
        supportLinearFiltering = glCtx.getExtension('OES_texture_half_float_linear')
      }
      glCtx.clearColor(0, 0, 0, 1)

      const halfFloatTexType = isWebGL2
        ? (glCtx as WebGL2RenderingContext).HALF_FLOAT
        : halfFloat?.HALF_FLOAT_OES ?? 0

      const getSupportedFormat = (g: WebGLAny, internalFormat: number, format: number, type: number): { internalFormat: number; format: number } | null => {
        if (!supportRenderTextureFormat(g, internalFormat, format, type)) {
          if (internalFormat === (g as WebGL2RenderingContext).R16F) return getSupportedFormat(g, (g as WebGL2RenderingContext).RG16F, (g as WebGL2RenderingContext).RG, type)
          if (internalFormat === (g as WebGL2RenderingContext).RG16F) return getSupportedFormat(g, (g as WebGL2RenderingContext).RGBA16F, g.RGBA, type)
          return null
        }
        return { internalFormat, format }
      }

      const supportRenderTextureFormat = (g: WebGLAny, internalFormat: number, format: number, type: number) => {
        const tex = g.createTexture()
        g.bindTexture(g.TEXTURE_2D, tex)
        g.texParameteri(g.TEXTURE_2D, g.TEXTURE_MIN_FILTER, g.NEAREST)
        g.texParameteri(g.TEXTURE_2D, g.TEXTURE_MAG_FILTER, g.NEAREST)
        g.texParameteri(g.TEXTURE_2D, g.TEXTURE_WRAP_S, g.CLAMP_TO_EDGE)
        g.texParameteri(g.TEXTURE_2D, g.TEXTURE_WRAP_T, g.CLAMP_TO_EDGE)
        g.texImage2D(g.TEXTURE_2D, 0, internalFormat, 4, 4, 0, format, type, null)
        const fbo = g.createFramebuffer()
        g.bindFramebuffer(g.FRAMEBUFFER, fbo)
        g.framebufferTexture2D(g.FRAMEBUFFER, g.COLOR_ATTACHMENT0, g.TEXTURE_2D, tex, 0)
        return g.checkFramebufferStatus(g.FRAMEBUFFER) === g.FRAMEBUFFER_COMPLETE
      }

      let formatRGBA, formatRG, formatR
      if (isWebGL2) {
        const g2 = glCtx as WebGL2RenderingContext
        formatRGBA = getSupportedFormat(g2, g2.RGBA16F, g2.RGBA, halfFloatTexType)
        formatRG   = getSupportedFormat(g2, g2.RG16F,   g2.RG,   halfFloatTexType)
        formatR    = getSupportedFormat(g2, g2.R16F,    g2.RED,  halfFloatTexType)
      } else {
        formatRGBA = getSupportedFormat(glCtx, glCtx.RGBA, glCtx.RGBA, halfFloatTexType)
        formatRG   = getSupportedFormat(glCtx, glCtx.RGBA, glCtx.RGBA, halfFloatTexType)
        formatR    = getSupportedFormat(glCtx, glCtx.RGBA, glCtx.RGBA, halfFloatTexType)
      }

      return { gl: glCtx, ext: { formatRGBA, formatRG, formatR, halfFloatTexType, supportLinearFiltering } }
    }

    const { gl, ext } = getWebGLContext(canvas)
    if (!ext.supportLinearFiltering) { config.DYE_RESOLUTION = 256; config.SHADING = false }

    // ── Shader helpers ───────────────────────────────────────
    const compileShader = (type: number, source: string, keywords?: string[]) => {
      let src = source
      if (keywords) src = keywords.map(k => `#define ${k}\n`).join('') + src
      const s = gl.createShader(type)!
      gl.shaderSource(s, src); gl.compileShader(s)
      return s
    }

    const createProgram = (vs: WebGLShader, fs: WebGLShader) => {
      const p = gl.createProgram()!
      gl.attachShader(p, vs); gl.attachShader(p, fs); gl.linkProgram(p)
      return p
    }

    const getUniforms = (p: WebGLProgram) => {
      const u: Record<string, WebGLUniformLocation | null> = {}
      const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS)
      for (let i = 0; i < n; i++) {
        const name = gl.getActiveUniform(p, i)!.name
        u[name] = gl.getUniformLocation(p, name)
      }
      return u
    }

    // ── Shaders ──────────────────────────────────────────────
    const baseVS = compileShader(gl.VERTEX_SHADER, `
      precision highp float;
      attribute vec2 aPosition;
      varying vec2 vUv, vL, vR, vT, vB;
      uniform vec2 texelSize;
      void main(){
        vUv=aPosition*.5+.5;
        vL=vUv-vec2(texelSize.x,0.);
        vR=vUv+vec2(texelSize.x,0.);
        vT=vUv+vec2(0.,texelSize.y);
        vB=vUv-vec2(0.,texelSize.y);
        gl_Position=vec4(aPosition,0.,1.);
      }`)

    const copyFS   = compileShader(gl.FRAGMENT_SHADER, `precision mediump float;precision mediump sampler2D;varying highp vec2 vUv;uniform sampler2D uTexture;void main(){gl_FragColor=texture2D(uTexture,vUv);}`)
    const clearFS  = compileShader(gl.FRAGMENT_SHADER, `precision mediump float;precision mediump sampler2D;varying highp vec2 vUv;uniform sampler2D uTexture;uniform float value;void main(){gl_FragColor=value*texture2D(uTexture,vUv);}`)

    const displayFSSrc = `
      precision highp float;precision highp sampler2D;
      varying vec2 vUv,vL,vR,vT,vB;
      uniform sampler2D uTexture;uniform vec2 texelSize;
      vec3 linearToGamma(vec3 c){c=max(c,vec3(0));return max(1.055*pow(c,vec3(.4166))-.055,vec3(0));}
      void main(){
        vec3 c=texture2D(uTexture,vUv).rgb;
        #ifdef SHADING
          vec3 lc=texture2D(uTexture,vL).rgb,rc=texture2D(uTexture,vR).rgb,
               tc=texture2D(uTexture,vT).rgb,bc=texture2D(uTexture,vB).rgb;
          float dx=length(rc)-length(lc),dy=length(tc)-length(bc);
          vec3 n=normalize(vec3(dx,dy,length(texelSize)));
          float d=clamp(dot(n,vec3(0,0,1))+.7,.7,1.);c*=d;
        #endif
        float a=max(c.r,max(c.g,c.b));gl_FragColor=vec4(c,a);}
    `
    const splatFS = compileShader(gl.FRAGMENT_SHADER, `
      precision highp float;precision highp sampler2D;
      varying vec2 vUv;uniform sampler2D uTarget;
      uniform float aspectRatio;uniform vec3 color;uniform vec2 point;uniform float radius;
      void main(){
        vec2 p=vUv-point.xy;p.x*=aspectRatio;
        vec3 s=exp(-dot(p,p)/radius)*color;
        gl_FragColor=vec4(texture2D(uTarget,vUv).xyz+s,1.);}`)

    const advectionFS = compileShader(gl.FRAGMENT_SHADER, `
      precision highp float;precision highp sampler2D;
      varying vec2 vUv;uniform sampler2D uVelocity,uSource;
      uniform vec2 texelSize,dyeTexelSize;uniform float dt,dissipation;
      vec4 bilerp(sampler2D s,vec2 uv,vec2 ts){
        vec2 st=uv/ts-.5;vec2 iuv=floor(st),fuv=fract(st);
        vec4 a=texture2D(s,(iuv+vec2(.5,.5))*ts),b=texture2D(s,(iuv+vec2(1.5,.5))*ts),
             c=texture2D(s,(iuv+vec2(.5,1.5))*ts),d=texture2D(s,(iuv+vec2(1.5,1.5))*ts);
        return mix(mix(a,b,fuv.x),mix(c,d,fuv.x),fuv.y);}
      void main(){
        #ifdef MANUAL_FILTERING
          vec2 coord=vUv-dt*bilerp(uVelocity,vUv,texelSize).xy*texelSize;
          vec4 r=bilerp(uSource,coord,dyeTexelSize);
        #else
          vec2 coord=vUv-dt*texture2D(uVelocity,vUv).xy*texelSize;
          vec4 r=texture2D(uSource,coord);
        #endif
        gl_FragColor=r/(1.+dissipation*dt);}`,
      ext.supportLinearFiltering ? undefined : ['MANUAL_FILTERING'])

    const divergenceFS = compileShader(gl.FRAGMENT_SHADER, `
      precision mediump float;precision mediump sampler2D;
      varying highp vec2 vUv,vL,vR,vT,vB;uniform sampler2D uVelocity;
      void main(){
        float L=texture2D(uVelocity,vL).x,R=texture2D(uVelocity,vR).x,
              T=texture2D(uVelocity,vT).y,B=texture2D(uVelocity,vB).y;
        vec2 C=texture2D(uVelocity,vUv).xy;
        if(vL.x<0.)L=-C.x;if(vR.x>1.)R=-C.x;if(vT.y>1.)T=-C.y;if(vB.y<0.)B=-C.y;
        gl_FragColor=vec4(.5*(R-L+T-B),0.,0.,1.);}`)

    const curlFS = compileShader(gl.FRAGMENT_SHADER, `
      precision mediump float;precision mediump sampler2D;
      varying highp vec2 vUv,vL,vR,vT,vB;uniform sampler2D uVelocity;
      void main(){
        float L=texture2D(uVelocity,vL).y,R=texture2D(uVelocity,vR).y,
              T=texture2D(uVelocity,vT).x,B=texture2D(uVelocity,vB).x;
        gl_FragColor=vec4(.5*(R-L-T+B),0.,0.,1.);}`)

    const vorticityFS = compileShader(gl.FRAGMENT_SHADER, `
      precision highp float;precision highp sampler2D;
      varying vec2 vUv,vL,vR,vT,vB;uniform sampler2D uVelocity,uCurl;
      uniform float curl,dt;
      void main(){
        float L=texture2D(uCurl,vL).x,R=texture2D(uCurl,vR).x,
              T=texture2D(uCurl,vT).x,B=texture2D(uCurl,vB).x,C=texture2D(uCurl,vUv).x;
        vec2 f=.5*vec2(abs(T)-abs(B),abs(R)-abs(L));
        f/=length(f)+.0001;f*=curl*C;f.y*=-1.;
        vec2 v=texture2D(uVelocity,vUv).xy+f*dt;
        gl_FragColor=vec4(clamp(v,-1e3,1e3),0.,1.);}`)

    const pressureFS = compileShader(gl.FRAGMENT_SHADER, `
      precision mediump float;precision mediump sampler2D;
      varying highp vec2 vUv,vL,vR,vT,vB;
      uniform sampler2D uPressure,uDivergence;
      void main(){
        float L=texture2D(uPressure,vL).x,R=texture2D(uPressure,vR).x,
              T=texture2D(uPressure,vT).x,B=texture2D(uPressure,vB).x,
              div=texture2D(uDivergence,vUv).x;
        gl_FragColor=vec4((L+R+B+T-div)*.25,0.,0.,1.);}`)

    const gradSubFS = compileShader(gl.FRAGMENT_SHADER, `
      precision mediump float;precision mediump sampler2D;
      varying highp vec2 vUv,vL,vR,vT,vB;
      uniform sampler2D uPressure,uVelocity;
      void main(){
        float L=texture2D(uPressure,vL).x,R=texture2D(uPressure,vR).x,
              T=texture2D(uPressure,vT).x,B=texture2D(uPressure,vB).x;
        vec2 v=texture2D(uVelocity,vUv).xy-vec2(R-L,T-B);
        gl_FragColor=vec4(v,0.,1.);}`)

    // ── Programs ─────────────────────────────────────────────
    const copyProg     = { p: createProgram(baseVS, copyFS),     u: {} as Record<string, WebGLUniformLocation | null> }
    const clearProg    = { p: createProgram(baseVS, clearFS),    u: {} as Record<string, WebGLUniformLocation | null> }
    const splatProg    = { p: createProgram(baseVS, splatFS),    u: {} as Record<string, WebGLUniformLocation | null> }
    const advProg      = { p: createProgram(baseVS, advectionFS),u: {} as Record<string, WebGLUniformLocation | null> }
    const divProg      = { p: createProgram(baseVS, divergenceFS),u: {} as Record<string, WebGLUniformLocation | null> }
    const curlProg     = { p: createProgram(baseVS, curlFS),     u: {} as Record<string, WebGLUniformLocation | null> }
    const vortProg     = { p: createProgram(baseVS, vorticityFS),u: {} as Record<string, WebGLUniformLocation | null> }
    const pressProg    = { p: createProgram(baseVS, pressureFS), u: {} as Record<string, WebGLUniformLocation | null> }
    const gradProg     = { p: createProgram(baseVS, gradSubFS),  u: {} as Record<string, WebGLUniformLocation | null> }

    ;[copyProg, clearProg, splatProg, advProg, divProg, curlProg, vortProg, pressProg, gradProg].forEach(prog => {
      prog.u = getUniforms(prog.p)
    })

    // Display material (supports SHADING keyword)
    const displayPrograms: Record<number, WebGLProgram> = {}
    let displayActive: WebGLProgram | null = null
    let displayUniforms: Record<string, WebGLUniformLocation | null> = {}

    const bindDisplay = () => {
      const hash = config.SHADING ? 1 : 0
      if (!displayPrograms[hash]) {
        const fs = compileShader(gl.FRAGMENT_SHADER, displayFSSrc, config.SHADING ? ['SHADING'] : undefined)
        displayPrograms[hash] = createProgram(baseVS, fs)
      }
      if (displayPrograms[hash] !== displayActive) {
        displayActive = displayPrograms[hash]
        displayUniforms = getUniforms(displayActive)
      }
      gl.useProgram(displayActive)
    }

    // ── Blit ─────────────────────────────────────────────────
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer())
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1,-1,1,1,1,1,-1]), gl.STATIC_DRAW)
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, gl.createBuffer())
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array([0,1,2,0,2,3]), gl.STATIC_DRAW)
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0)
    gl.enableVertexAttribArray(0)

    interface FBO {
      texture: WebGLTexture; fbo: WebGLFramebuffer
      width: number; height: number
      texelSizeX: number; texelSizeY: number
      attach(id: number): number
    }
    interface DoubleFBO {
      width: number; height: number; texelSizeX: number; texelSizeY: number
      read: FBO; write: FBO; swap(): void
    }

    const blit = (target: FBO | null, clear = false) => {
      if (!target) {
        gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight)
        gl.bindFramebuffer(gl.FRAMEBUFFER, null)
      } else {
        gl.viewport(0, 0, target.width, target.height)
        gl.bindFramebuffer(gl.FRAMEBUFFER, target.fbo)
      }
      if (clear) { gl.clearColor(0,0,0,1); gl.clear(gl.COLOR_BUFFER_BIT) }
      gl.drawElements(gl.TRIANGLES, 6, gl.UNSIGNED_SHORT, 0)
    }

    const createFBO = (w: number, h: number, internalFormat: number, format: number, type: number, param: number): FBO => {
      gl.activeTexture(gl.TEXTURE0)
      const tex = gl.createTexture()!
      gl.bindTexture(gl.TEXTURE_2D, tex)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, param)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, param)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
      gl.texImage2D(gl.TEXTURE_2D, 0, internalFormat, w, h, 0, format, type, null)
      const fbo = gl.createFramebuffer()!
      gl.bindFramebuffer(gl.FRAMEBUFFER, fbo)
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0)
      gl.viewport(0, 0, w, h); gl.clear(gl.COLOR_BUFFER_BIT)
      return {
        texture: tex, fbo, width: w, height: h,
        texelSizeX: 1/w, texelSizeY: 1/h,
        attach(id) { gl.activeTexture(gl.TEXTURE0+id); gl.bindTexture(gl.TEXTURE_2D, tex); return id },
      }
    }

    const createDoubleFBO = (w: number, h: number, iF: number, f: number, t: number, p: number): DoubleFBO => {
      let fbo1 = createFBO(w,h,iF,f,t,p), fbo2 = createFBO(w,h,iF,f,t,p)
      return {
        width:w, height:h, texelSizeX:fbo1.texelSizeX, texelSizeY:fbo1.texelSizeY,
        get read(){ return fbo1 }, set read(v){ fbo1=v },
        get write(){ return fbo2 }, set write(v){ fbo2=v },
        swap(){ const tmp=fbo1; fbo1=fbo2; fbo2=tmp },
      }
    }

    const resizeFBO = (target: FBO, w: number, h: number, iF: number, f: number, t: number, p: number): FBO => {
      const n = createFBO(w,h,iF,f,t,p)
      gl.useProgram(copyProg.p)
      gl.uniform1i(copyProg.u['uTexture'], target.attach(0))
      blit(n); return n
    }

    const resizeDoubleFBO = (target: DoubleFBO, w: number, h: number, iF: number, f: number, t: number, p: number): DoubleFBO => {
      if (target.width===w && target.height===h) return target
      target.read = resizeFBO(target.read,w,h,iF,f,t,p)
      target.write = createFBO(w,h,iF,f,t,p)
      target.width=w; target.height=h; target.texelSizeX=1/w; target.texelSizeY=1/h
      return target
    }

    const getResolution = (res: number) => {
      let ar = gl.drawingBufferWidth/gl.drawingBufferHeight
      if (ar<1) ar=1/ar
      const min=Math.round(res), max=Math.round(res*ar)
      return gl.drawingBufferWidth>gl.drawingBufferHeight ? {width:max,height:min} : {width:min,height:max}
    }

    const scale = (input: number) => Math.floor(input*(window.devicePixelRatio||1))

    // ── Framebuffers ─────────────────────────────────────────
    let dye: DoubleFBO, velocity: DoubleFBO, divergence: FBO, curl: FBO, pressure: DoubleFBO

    const initFBOs = () => {
      const simRes = getResolution(config.SIM_RESOLUTION)
      const dyeRes = getResolution(config.DYE_RESOLUTION)
      const t = ext.halfFloatTexType
      const rgba = ext.formatRGBA!, rg = ext.formatRG!, r = ext.formatR!
      const filter = ext.supportLinearFiltering ? gl.LINEAR : gl.NEAREST
      gl.disable(gl.BLEND)

      dye      = dye ? resizeDoubleFBO(dye,dyeRes.width,dyeRes.height,rgba.internalFormat,rgba.format,t,filter)
                     : createDoubleFBO(dyeRes.width,dyeRes.height,rgba.internalFormat,rgba.format,t,filter)
      velocity = velocity ? resizeDoubleFBO(velocity,simRes.width,simRes.height,rg.internalFormat,rg.format,t,filter)
                          : createDoubleFBO(simRes.width,simRes.height,rg.internalFormat,rg.format,t,filter)
      divergence = createFBO(simRes.width,simRes.height,r.internalFormat,r.format,t,gl.NEAREST)
      curl       = createFBO(simRes.width,simRes.height,r.internalFormat,r.format,t,gl.NEAREST)
      pressure   = createDoubleFBO(simRes.width,simRes.height,r.internalFormat,r.format,t,gl.NEAREST)
    }

    initFBOs()

    // ── Color helpers ─────────────────────────────────────────
    const HSVtoRGB = (h: number, s: number, v: number) => {
      const i=Math.floor(h*6), f=h*6-i, p=v*(1-s), q=v*(1-f*s), t2=v*(1-(1-f)*s)
      const cases: [number,number,number][] = [[v,t2,p],[q,v,p],[p,v,t2],[p,q,v],[t2,p,v],[v,p,q]]
      const [r,g,b] = cases[i%6]
      return { r: r*.15, g: g*.15, b: b*.15 }
    }

    const hexToRGB = (hex: string) => {
      const v = hex.replace('#','').padEnd(6,'0')
      return {
        r: parseInt(v.slice(0,2),16)/255*.15,
        g: parseInt(v.slice(2,4),16)/255*.15,
        b: parseInt(v.slice(4,6),16)/255*.15,
      }
    }

    const generateColor = () => RAINBOW_MODE
      ? HSVtoRGB(Math.random(),1,1)
      : hexToRGB(COLOR)

    // ── Simulation ────────────────────────────────────────────
    const splat = (x: number, y: number, dx: number, dy: number, color: { r:number; g:number; b:number }) => {
      gl.useProgram(splatProg.p)
      gl.uniform1i(splatProg.u['uTarget'], velocity.read.attach(0))
      gl.uniform1f(splatProg.u['aspectRatio'] as WebGLUniformLocation, canvas.width/canvas.height)
      gl.uniform2f(splatProg.u['point'] as WebGLUniformLocation, x, y)
      gl.uniform3f(splatProg.u['color'] as WebGLUniformLocation, dx, dy, 0)
      const rr = config.SPLAT_RADIUS/100*(canvas.width/canvas.height>1?canvas.width/canvas.height:1)
      gl.uniform1f(splatProg.u['radius'] as WebGLUniformLocation, rr)
      blit(velocity.write); velocity.swap()

      gl.uniform1i(splatProg.u['uTarget'], dye.read.attach(0))
      gl.uniform3f(splatProg.u['color'] as WebGLUniformLocation, color.r, color.g, color.b)
      blit(dye.write); dye.swap()
    }

    const step = (dt: number) => {
      gl.disable(gl.BLEND)

      gl.useProgram(curlProg.p)
      gl.uniform2f(curlProg.u['texelSize'] as WebGLUniformLocation, velocity.texelSizeX, velocity.texelSizeY)
      gl.uniform1i(curlProg.u['uVelocity'], velocity.read.attach(0))
      blit(curl)

      gl.useProgram(vortProg.p)
      gl.uniform2f(vortProg.u['texelSize'] as WebGLUniformLocation, velocity.texelSizeX, velocity.texelSizeY)
      gl.uniform1i(vortProg.u['uVelocity'], velocity.read.attach(0))
      gl.uniform1i(vortProg.u['uCurl'], curl.attach(1))
      gl.uniform1f(vortProg.u['curl'] as WebGLUniformLocation, config.CURL)
      gl.uniform1f(vortProg.u['dt'] as WebGLUniformLocation, dt)
      blit(velocity.write); velocity.swap()

      gl.useProgram(divProg.p)
      gl.uniform2f(divProg.u['texelSize'] as WebGLUniformLocation, velocity.texelSizeX, velocity.texelSizeY)
      gl.uniform1i(divProg.u['uVelocity'], velocity.read.attach(0))
      blit(divergence)

      gl.useProgram(clearProg.p)
      gl.uniform1i(clearProg.u['uTexture'], pressure.read.attach(0))
      gl.uniform1f(clearProg.u['value'] as WebGLUniformLocation, config.PRESSURE)
      blit(pressure.write); pressure.swap()

      gl.useProgram(pressProg.p)
      gl.uniform2f(pressProg.u['texelSize'] as WebGLUniformLocation, velocity.texelSizeX, velocity.texelSizeY)
      gl.uniform1i(pressProg.u['uDivergence'], divergence.attach(0))
      for (let i=0;i<config.PRESSURE_ITERATIONS;i++) {
        gl.uniform1i(pressProg.u['uPressure'], pressure.read.attach(1))
        blit(pressure.write); pressure.swap()
      }

      gl.useProgram(gradProg.p)
      gl.uniform2f(gradProg.u['texelSize'] as WebGLUniformLocation, velocity.texelSizeX, velocity.texelSizeY)
      gl.uniform1i(gradProg.u['uPressure'], pressure.read.attach(0))
      gl.uniform1i(gradProg.u['uVelocity'], velocity.read.attach(1))
      blit(velocity.write); velocity.swap()

      gl.useProgram(advProg.p)
      gl.uniform2f(advProg.u['texelSize'] as WebGLUniformLocation, velocity.texelSizeX, velocity.texelSizeY)
      if (!ext.supportLinearFiltering)
        gl.uniform2f(advProg.u['dyeTexelSize'] as WebGLUniformLocation, velocity.texelSizeX, velocity.texelSizeY)
      const vid = velocity.read.attach(0)
      gl.uniform1i(advProg.u['uVelocity'], vid)
      gl.uniform1i(advProg.u['uSource'], vid)
      gl.uniform1f(advProg.u['dt'] as WebGLUniformLocation, dt)
      gl.uniform1f(advProg.u['dissipation'] as WebGLUniformLocation, config.VELOCITY_DISSIPATION)
      blit(velocity.write); velocity.swap()

      if (!ext.supportLinearFiltering)
        gl.uniform2f(advProg.u['dyeTexelSize'] as WebGLUniformLocation, dye.texelSizeX, dye.texelSizeY)
      gl.uniform1i(advProg.u['uVelocity'], velocity.read.attach(0))
      gl.uniform1i(advProg.u['uSource'], dye.read.attach(1))
      gl.uniform1f(advProg.u['dissipation'] as WebGLUniformLocation, config.DENSITY_DISSIPATION)
      blit(dye.write); dye.swap()
    }

    const render = () => {
      gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
      gl.enable(gl.BLEND)
      bindDisplay()
      if (config.SHADING) gl.uniform2f(displayUniforms['texelSize'] as WebGLUniformLocation, 1/gl.drawingBufferWidth, 1/gl.drawingBufferHeight)
      gl.uniform1i(displayUniforms['uTexture'], dye.read.attach(0))
      blit(null)
    }

    // ── Pointer helpers ───────────────────────────────────────
    const updateDown = (ptr: PointerData, id: number, x: number, y: number) => {
      ptr.id=id; ptr.down=true; ptr.moved=false
      ptr.texcoordX=x/canvas.width; ptr.texcoordY=1-y/canvas.height
      ptr.prevTexcoordX=ptr.texcoordX; ptr.prevTexcoordY=ptr.texcoordY
      ptr.deltaX=0; ptr.deltaY=0; ptr.color=generateColor()
    }

    const ar = () => canvas.width/canvas.height
    const updateMove = (ptr: PointerData, x: number, y: number) => {
      ptr.prevTexcoordX=ptr.texcoordX; ptr.prevTexcoordY=ptr.texcoordY
      ptr.texcoordX=x/canvas.width; ptr.texcoordY=1-y/canvas.height
      let dx=ptr.texcoordX-ptr.prevTexcoordX, dy=ptr.texcoordY-ptr.prevTexcoordY
      const ratio=ar()
      if (ratio<1) dx*=ratio; if (ratio>1) dy/=ratio
      ptr.deltaX=dx; ptr.deltaY=dy
      ptr.moved=Math.abs(dx)>0||Math.abs(dy)>0
    }

    const clickSplat = (ptr: PointerData) => {
      const c=generateColor(); c.r*=10; c.g*=10; c.b*=10
      splat(ptr.texcoordX, ptr.texcoordY, 10*(Math.random()-.5), 30*(Math.random()-.5), c)
    }

    // ── Event handlers ────────────────────────────────────────
    const onMouseDown = (e: MouseEvent) => {
      const p=pointers[0]; updateDown(p,-1,scale(e.clientX),scale(e.clientY)); clickSplat(p)
    }
    let firstMove=false
    const onMouseMove = (e: MouseEvent) => {
      const p=pointers[0]
      if (!firstMove) { firstMove=true; p.color=generateColor() }
      updateMove(p, scale(e.clientX), scale(e.clientY))
    }
    const onTouchStart = (e: TouchEvent) => {
      Array.from(e.targetTouches).forEach(t =>
        updateDown(pointers[0], t.identifier, scale(t.clientX), scale(t.clientY)))
    }
    const onTouchMove = (e: TouchEvent) => {
      Array.from(e.targetTouches).forEach(t =>
        updateMove(pointers[0], scale(t.clientX), scale(t.clientY)))
    }
    const onTouchEnd = () => { pointers[0].down=false }

    window.addEventListener('mousedown',   onMouseDown)
    window.addEventListener('mousemove',   onMouseMove)
    window.addEventListener('touchstart',  onTouchStart)
    window.addEventListener('touchmove',   onTouchMove, { passive: false })
    window.addEventListener('touchend',    onTouchEnd)

    // ── Loop ──────────────────────────────────────────────────
    let lastTime=Date.now(), colorTimer=0

    const loop = () => {
      if (!isActive) return
      const now=Date.now(), dt=Math.min((now-lastTime)/1000, 0.016666)
      lastTime=now

      // Resize
      const w=scale(canvas.clientWidth), h=scale(canvas.clientHeight)
      if (canvas.width!==w||canvas.height!==h) { canvas.width=w; canvas.height=h; initFBOs() }

      // Update colors
      colorTimer+=dt*config.COLOR_UPDATE_SPEED
      if (colorTimer>=1) { colorTimer=0; pointers.forEach(p => { p.color=generateColor() }) }

      // Apply inputs
      pointers.forEach(p => { if (p.moved) { p.moved=false; splat(p.texcoordX,p.texcoordY,p.deltaX*config.SPLAT_FORCE,p.deltaY*config.SPLAT_FORCE,p.color) } })

      step(dt)
      render()
      rafRef.current = requestAnimationFrame(loop)
    }

    rafRef.current = requestAnimationFrame(loop)

    return () => {
      isActive=false
      cancelAnimationFrame(rafRef.current)
      window.removeEventListener('mousedown',  onMouseDown)
      window.removeEventListener('mousemove',  onMouseMove)
      window.removeEventListener('touchstart', onTouchStart)
      window.removeEventListener('touchmove',  onTouchMove)
      window.removeEventListener('touchend',   onTouchEnd)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div style={{ position:'fixed', top:0, left:0, zIndex:50, pointerEvents:'none', width:'100%', height:'100%' }}>
      <canvas
        ref={canvasRef}
        style={{ width:'100vw', height:'100vh', display:'block', background:'transparent' }}
      />
    </div>
  )
}
