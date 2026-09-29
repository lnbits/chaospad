/* Live controls use the pad's existing WebSocket, independently of speech. */
window.chaospadTeleprompter = {
  data() {
    return {
      teleprompter: {active: false, running: false, speed: 140, position: 0},
      teleprompterConnected: false,
      teleprompterEnded: false,
      teleprompterMirror: 'off'
    }
  },
  computed: {
    teleprompterWords() {
      return this.padText.match(/\S+\s*/gu) || []
    },
    teleprompterPlaying() {
      return this.teleprompter.running && !this.teleprompterEnded
    }
  },
  watch: {
    padText() {
      if (this.teleprompter.active) this.$nextTick(this.measureTeleprompter)
    }
  },
  methods: {
    sendTeleprompter(action) {
      if (this.ws?.readyState !== WebSocket.OPEN) return
      const command = new TextEncoder().encode(action)
      const frame = new Uint8Array(command.length + 1)
      frame[0] = 0x03
      frame.set(command, 1)
      this.ws.send(frame)
    },
    receiveTeleprompter(payload) {
      try {
        const state = JSON.parse(new TextDecoder().decode(payload))
        if (
          typeof state.active !== 'boolean' ||
          typeof state.running !== 'boolean' ||
          !Number.isFinite(state.position) ||
          state.position < 0 ||
          !Number.isFinite(state.speed) ||
          state.speed < 40 ||
          state.speed > 300
        )
          return
        this.teleprompter = state
        this._teleprompterReceivedAt = performance.now()
        this.teleprompterConnected = true
        if (state.active) this.$nextTick(this.drawTeleprompter)
      } catch {}
    },
    teleprompterPosition() {
      const state = this.teleprompter
      const elapsed =
        state.running && this.teleprompterConnected
          ? Math.max(0, performance.now() - this._teleprompterReceivedAt) / 1000
          : 0
      return state.position + (elapsed * state.speed) / 60
    },
    disconnectTeleprompter() {
      this.teleprompter.position = this.teleprompterPosition()
      this.teleprompterConnected = false
      cancelAnimationFrame(this._teleprompterFrame)
    },
    toggleTeleprompter() {
      this.sendTeleprompter(
        this.teleprompterEnded
          ? 'restart'
          : this.teleprompter.running
            ? 'pause'
            : 'play'
      )
    },
    cancelTeleprompter() {
      if (this.teleprompterConnected) this.sendTeleprompter('cancel')
      else this.teleprompter.active = false
    },
    startTeleprompterView() {
      this._teleprompterResize?.disconnect()
      this._teleprompterResize = new ResizeObserver(this.measureTeleprompter)
      this._teleprompterResize.observe(this.$refs.teleprompterViewport)
      this.measureTeleprompter()
      this.keepTeleprompterAwake()
    },
    stopTeleprompterView() {
      cancelAnimationFrame(this._teleprompterFrame)
      this._teleprompterResize?.disconnect()
      this._teleprompterWakeLock?.release().catch(() => {})
      this._teleprompterWakeLock = null
    },
    async keepTeleprompterAwake() {
      if (!this.teleprompter.active || document.hidden || !navigator.wakeLock)
        return
      if (this._teleprompterWakeLock && !this._teleprompterWakeLock.released)
        return
      try {
        const lock = await navigator.wakeLock.request('screen')
        if (this.teleprompter.active) this._teleprompterWakeLock = lock
        else await lock.release()
      } catch {}
    },
    measureTeleprompter() {
      const script = this.$refs.teleprompterScript
      if (!script) return
      const lines = []
      // Group word offsets into this screen's lines; other screens may wrap differently.
      Array.from(script.children).forEach((word, index) => {
        const top = word.offsetTop
        if (!lines.length || lines[lines.length - 1].top !== top) {
          lines.push({word: index, top})
        }
      })
      if (lines.length) {
        const last = lines[lines.length - 1]
        lines.push({
          word: this.teleprompterWords.length,
          top: last.top + parseFloat(getComputedStyle(script).lineHeight)
        })
      }
      this._teleprompterLines = lines
      this.drawTeleprompter()
    },
    drawTeleprompter() {
      cancelAnimationFrame(this._teleprompterFrame)
      const viewport = this.$refs.teleprompterViewport
      const lines = this._teleprompterLines || []
      if (!this.teleprompter.active || !viewport || lines.length < 2) return
      const position = Math.min(
        this.teleprompterPosition(),
        this.teleprompterWords.length
      )
      this.teleprompterEnded = position >= this.teleprompterWords.length
      let index = 0
      while (index < lines.length - 2 && lines[index + 1].word <= position)
        index++
      const line = lines[index]
      const next = lines[index + 1]
      const fraction = (position - line.word) / (next.word - line.word)
      viewport.scrollTop =
        line.top - lines[0].top + fraction * (next.top - line.top)
      if (this.teleprompterPlaying && this.teleprompterConnected) {
        this._teleprompterFrame = requestAnimationFrame(this.drawTeleprompter)
      }
    },
    resyncTeleprompter() {
      if (!document.hidden) {
        this.sendTeleprompter('sync')
        this.keepTeleprompterAwake()
      }
    }
  },
  mounted() {
    document.addEventListener('visibilitychange', this.resyncTeleprompter)
  },
  unmounted() {
    this.stopTeleprompterView()
    document.removeEventListener('visibilitychange', this.resyncTeleprompter)
  }
}
