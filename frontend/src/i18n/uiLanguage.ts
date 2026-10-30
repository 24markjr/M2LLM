/**
 * The console's language (v4 Phase 7): one choice, made in the top bar or in Settings, followed by
 * the menu, the home page and the case conversation. Remembered in this browser; every part of the
 * screen hears a change at once. Hindi has its own interface words; any other Indian language
 * keeps the English interface, while questions and answers still go in that language.
 */

import { useEffect, useState } from "react";

import { rememberLanguage, rememberedLanguage } from "../pages/talkWords";

export const LANGUAGE_EVENT = "jarvis:language";

/** The languages offered, as the language layer offers them (`app/language/detect.py`). */
export const UI_LANGUAGES: { code: string; native: string; name: string; short: string }[] = [
  { code: "", native: "English", name: "English", short: "EN" },
  { code: "hi", native: "हिन्दी", name: "Hindi", short: "हि" },
  { code: "mr", native: "मराठी", name: "Marathi", short: "म" },
  { code: "bn", native: "বাংলা", name: "Bengali", short: "বা" },
  { code: "ta", native: "தமிழ்", name: "Tamil", short: "த" },
  { code: "te", native: "తెలుగు", name: "Telugu", short: "తె" },
  { code: "kn", native: "ಕನ್ನಡ", name: "Kannada", short: "ಕ" },
  { code: "ml", native: "മലയാളം", name: "Malayalam", short: "മ" },
  { code: "gu", native: "ગુજરાતી", name: "Gujarati", short: "ગુ" },
  { code: "pa", native: "ਪੰਜਾਬੀ", name: "Punjabi", short: "ਪੰ" },
  { code: "or", native: "ଓଡ଼ିଆ", name: "Odia", short: "ଓ" },
  { code: "as", native: "অসমীয়া", name: "Assamese", short: "অ" },
  { code: "ne", native: "नेपाली", name: "Nepali", short: "ने" },
  { code: "ur", native: "اردو", name: "Urdu", short: "ار" },
];

export function setUiLanguage(code: string): void {
  rememberLanguage(code);
  window.dispatchEvent(new CustomEvent(LANGUAGE_EVENT, { detail: code }));
}

/** The chosen language, kept current as it changes anywhere on the page. */
export function useUiLanguage(): [string, (code: string) => void] {
  const [language, setLanguage] = useState(rememberedLanguage);
  useEffect(() => {
    const changed = (e: Event) => setLanguage((e as CustomEvent<string>).detail ?? "");
    window.addEventListener(LANGUAGE_EVENT, changed);
    return () => window.removeEventListener(LANGUAGE_EVENT, changed);
  }, []);
  return [language, setUiLanguage];
}

export interface ShellWords {
  newInvestigation: string;
  search: string;
  library: string;
  insights: string;
  activity: string;
  settings: string;
  cases: string;
  allCases: string;
  signOut: string;
  language: string;
  homeTitle: string;
  homeLead: string;
  tryQuestion: string;
  languageNote: string;
}

const ENGLISH: ShellWords = {
  newInvestigation: "New investigation",
  search: "Search",
  library: "Library",
  insights: "Insights",
  activity: "Activity",
  settings: "Settings",
  cases: "Cases",
  allCases: "All cases",
  signOut: "Sign out",
  language: "Language",
  homeTitle: "What do you need to find out?",
  homeLead:
    "Ask a question and attach the files. JARVIS plans the work, reads every file, checks each finding against the lines it cites, and tells you what it could not establish.",
  tryQuestion: "Try a question",
  languageNote:
    "Questions can be asked in this language, typed, in Roman letters or spoken; answers and reports come in it, labelled as translations of the verified English.",
};

const HINDI: ShellWords = {
  newInvestigation: "नई जाँच",
  search: "खोजें",
  library: "पुस्तकालय",
  insights: "अंतर्दृष्टि",
  activity: "गतिविधि",
  settings: "सेटिंग्स",
  cases: "मामले",
  allCases: "सभी मामले",
  signOut: "साइन आउट",
  language: "भाषा",
  homeTitle: "आपको क्या पता करना है?",
  homeLead:
    "प्रश्न पूछें और फ़ाइलें जोड़ें। JARVIS काम की योजना बनाता है, हर फ़ाइल पढ़ता है, हर निष्कर्ष को उन पंक्तियों से जाँचता है जिनका वह हवाला देता है, और बताता है कि क्या स्थापित नहीं हो सका।",
  tryQuestion: "एक प्रश्न आज़माएँ",
  languageNote:
    "प्रश्न इस भाषा में पूछे जा सकते हैं - लिखकर, रोमन अक्षरों में या बोलकर; उत्तर और रिपोर्ट इसी भाषा में आते हैं, सत्यापित अंग्रेज़ी के अनुवाद के रूप में चिह्नित।",
};

export function shellWords(language: string): ShellWords {
  return language === "hi" ? HINDI : ENGLISH;
}
