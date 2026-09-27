(function (root) {
  'use strict';
  // Realtime transcripts are cumulative replacements, not new chat messages.
  class VoiceTranscript {
    constructor() { this.clear(); }
    clear() { this.rows = new Map(); this.active = {}; }
    begin(role) { delete this.active[role]; }
    update(messages, role, text, itemId) {
      if (!text) return null;
      const key = itemId ? role + ':' + itemId : null;
      let row = key ? this.rows.get(key) : this.active[role];
      // Some streams repeat completed/cumulative captions under another ID.
      // Coalesce only an immediately preceding user caption; never cross a reply.
      const last = messages[messages.length - 1];
      if (!row && role === 'user' && last?.source === 'grok' && last.role === role &&
          text.startsWith(last.text)) row = last;
      if (!row) { row = {role, text:'', source:'grok'}; messages.push(row); }
      row.text = text;
      this.active[role] = row;
      if (key) {
        this.rows.set(key, row);
        if (this.rows.size > 256) this.rows.delete(this.rows.keys().next().value);
      }
      return row;
    }
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = VoiceTranscript;
  else root.BenchyVoiceTranscript = VoiceTranscript;
})(typeof window !== 'undefined' ? window : globalThis);
