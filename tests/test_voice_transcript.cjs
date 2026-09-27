const test = require('node:test');
const assert = require('node:assert/strict');
const VoiceTranscript = require('../benchos/dashboard_ui/voice-transcript.js');

test('streamed captions and repeated completion replace one turn', () => {
  const transcript = new VoiceTranscript(), messages = [];
  for (const text of ['Check the', 'Check the alarm frequency', 'Check the alarm frequency with the real probe'])
    transcript.update(messages, 'user', text, 'audio-1');
  transcript.begin('user');
  transcript.update(messages, 'user', 'Check the alarm frequency with the real probe', 'audio-1');
  assert.equal(messages.length, 1);
  assert.equal(messages[0].text, 'Check the alarm frequency with the real probe');
});

test('cumulative completed captions without stable IDs do not stack', () => {
  const transcript = new VoiceTranscript(), messages = [];
  for (const [index,text] of ['Check the', 'Check the alarm', 'Check the alarm frequency', 'Check the alarm frequency'].entries()) {
    transcript.update(messages, 'user', text, 'partial-'+index);
    transcript.begin('user');
  }
  assert.equal(messages.length, 1);
  assert.equal(messages[0].text, 'Check the alarm frequency');
});

test('corrected captions may shrink and late completion keeps turn order', () => {
  const transcript = new VoiceTranscript(), messages = [];
  transcript.update(messages, 'user', 'Check the alarming water reading', 'audio-1');
  transcript.update(messages, 'assistant', 'Measuring now.', 'answer-1');
  transcript.update(messages, 'user', 'Check the alarm.', 'audio-1');
  assert.equal(messages.length, 2);
  assert.equal(messages[0].text, 'Check the alarm.');
  assert.equal(messages[1].text, 'Measuring now.');
});

test('new speech after a reply remains distinct and clear forgets old IDs', () => {
  const transcript = new VoiceTranscript(), messages = [];
  transcript.update(messages, 'user', 'Test', 'audio-1');
  transcript.update(messages, 'assistant', 'Ready.', 'answer-1');
  transcript.begin('user');
  transcript.update(messages, 'user', 'Test', 'audio-2');
  assert.equal(messages.length, 3);
  transcript.clear();
  const fresh=[];
  transcript.update(fresh,'user','New chat','audio-1');
  assert.equal(fresh.length,1);
  assert.equal(messages[0].text,'Test');
});
