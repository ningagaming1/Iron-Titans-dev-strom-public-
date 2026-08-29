"""
tts.py - a drop-in text-to-speech module for the voice pipeline.

    mic -> STT -> text -> website shows it -> THIS: speak it back
                                           -> user confirms -> backend

Two engines behind one TextToSpeech class so you can swap them:
    offline -> pyttsx3  (no internet, instant, robotic)
    online  -> gTTS     (needs internet, google voice, more natural)
"""

import os
import tempfile


class TextToSpeech:
    def __init__(self, engine="offline", rate=150, volume=1.0, voice_lang="en"):
        """
        engine: "offline" (pyttsx3) or "online" (gTTS).
        rate: speaking speed (offline only).
        volume: 0.0 to 1.0 (offline engine only).
        voice_lang: language code ("en" for English; mostly used by online engines).

        """
        self.engine_type = engine
        self.voice_lang = voice_lang


        if self.engine_type == "offline":
            import pyttsx3
            self.engine = pyttsx3.init()
            self.engine.setProperty("rate", rate)
            self.engine.setProperty("volume", volume)
        elif self.engine_type == "online":
            from gtts import gTTS
            self.gTTS = gTTS
        else:
            raise ValueError("engine must be 'offline' or 'online'")

        """Speak `text` out loud immediately."""

        if not text or not text.strip():
            raise ValueError("No text provided to speak.")
        
        #for offline engine
        if self.engine_type == "offline":
            self.engine.say(text)
            self.engine.runAndWait()
        else:
            # online: render to a temp file, play it, delete it

            path = self.save(text)
            self._play_audio_file(path)
            os.remove(path)

    # save to an audio file (for the backend, or to feed back into STT)
    def save(self, text: str, filename: str = None) -> str:
        """
        Render `text` to an audio file and return its path. Used for backend or to feed back into STT.
        No filename given -> a temp .wav/.mp3 is made for you.

        """
        if not text or not text.strip():
            raise ValueError("No text provided to save.")

        if self.engine_type == "offline":
            filename = filename or self._temp_path(".wav")
            self.engine.save_to_file(text, filename)
            self.engine.runAndWait()
        #if online
        else:
            filename = filename or self._temp_path(".mp3")
            tts = self.gTTS(text=text, lang=self.voice_lang)
            tts.save(filename)

        return filename

    # play any audio file (used by the online engine)

    def _play_audio_file(self, path: str):
        from playsound import playsound
        playsound(path)

    def _temp_path(self, ext: str) -> str:
        fd, path = tempfile.mkstemp(suffix=ext)
        os.close(fd)
        return path


# example: STT -> website -> backend flow
if __name__ == "__main__":
    # hardcoded for now; later swap in your real STT call
    recognized_text = "This is the text that came from the speech to text module."

    tts = TextToSpeech(engine="offline")   # "online" for gTTS

    # let the user rehear what was recognized
    tts.speak(recognized_text)

    # save it too, in case the backend wants an audio file
    audio_path = tts.save(recognized_text, filename="confirmed_output.wav")
    print(f"Saved audio for backend at: {audio_path}")

    # then send recognized_text and/or audio_path to your backend

