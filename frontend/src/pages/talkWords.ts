/**
 * The conversation panel's own words, in the language the person chose (v4 Phase 7). English and
 * Hindi; any other language shows the English words, while questions and answers still go in it.
 * Evidence, citations and statuses are never translated here - they are what the answer rests on.
 */

export interface TalkWords {
  title: string;
  questions: string;
  intro: string;
  placeholder: string;
  answerPrefix: string;
  ask: string;
  working: string;
  speak: string;
  stop: string;
  listening: string;
  transcribing: string;
  readAloud: string;
  language: string;
  detect: string;
  readInEnglish: string;
  typedAs: string;
  askAgain: string;
  pin: string;
  unpin: string;
  edit: string;
  askInstead: string;
  cancel: string;
  translationLabel: string;
  micUnavailable: string;
}

const ENGLISH: TalkWords = {
  title: "Ask about this case",
  questions: "question(s)",
  intro:
    'Ask about the case\'s documents and findings. Every claim in an answer is checked against the lines it cites before it is marked. Name a finding to re-check it: "recheck F-002".',
  placeholder: "Ask about this case",
  answerPrefix: "Answer",
  ask: "Ask",
  working: "Working.",
  speak: "Speak",
  stop: "Stop",
  listening: "Listening... press Stop when you have finished",
  transcribing: "Writing down what you said",
  readAloud: "Read aloud",
  language: "Language",
  detect: "English, or detect from what I type",
  readInEnglish: "Read in English as",
  typedAs: "typed as",
  askAgain: "ask again",
  pin: "pin",
  unpin: "unpin",
  edit: "edit",
  askInstead: "Ask this instead",
  cancel: "cancel",
  translationLabel: "Machine translation of the verified English answer",
  micUnavailable: "This browser cannot record here; type the question instead.",
};

const HINDI: TalkWords = {
  title: "इस मामले के बारे में पूछें",
  questions: "प्रश्न",
  intro:
    'मामले के दस्तावेज़ों और निष्कर्षों के बारे में पूछें। उत्तर का हर दावा चिह्नित होने से पहले उन पंक्तियों से जाँचा जाता है जिनका वह हवाला देता है। किसी निष्कर्ष को दोबारा जाँचने के लिए उसका नाम लिखें: "recheck F-002"।',
  placeholder: "इस मामले के बारे में पूछें",
  answerPrefix: "उत्तर दें",
  ask: "पूछें",
  working: "काम जारी है।",
  speak: "बोलें",
  stop: "रोकें",
  listening: "सुन रहे हैं... बोलना पूरा होने पर रोकें दबाएँ",
  transcribing: "आपकी बात लिखी जा रही है",
  readAloud: "सुनें",
  language: "भाषा",
  detect: "अंग्रेज़ी, या जो लिखूँ उससे पहचानें",
  readInEnglish: "अंग्रेज़ी में ऐसे पढ़ा गया",
  typedAs: "ऐसे लिखा गया",
  askAgain: "फिर पूछें",
  pin: "पिन करें",
  unpin: "पिन हटाएँ",
  edit: "बदलें",
  askInstead: "इसके बजाय यह पूछें",
  cancel: "रद्द करें",
  translationLabel: "सत्यापित अंग्रेज़ी उत्तर का मशीनी अनुवाद",
  micUnavailable: "यह ब्राउज़र यहाँ रिकॉर्ड नहीं कर सकता; प्रश्न लिखकर पूछें।",
};

const WORDS: Record<string, TalkWords> = { en: ENGLISH, hi: HINDI };

export function talkWords(language: string): TalkWords {
  return WORDS[language] ?? ENGLISH;
}

const STORE = "jarvis:talk-language";

/** The language this viewer last chose; a convenience, so it never fails. */
export function rememberedLanguage(): string {
  try {
    return window.localStorage.getItem(STORE) ?? "";
  } catch {
    return "";
  }
}

export function rememberLanguage(code: string): void {
  try {
    window.localStorage.setItem(STORE, code);
  } catch {
    // Private windows and blocked storage: the choice simply is not remembered.
  }
}
