"""
text_to_speech.py
------------------
A drop-in Text-to-Speech (TTS) module designed to plug into a voice pipeline
that already has a Speech-to-Text (STT) module.

Pipeline this fits into:

    [Mic Input] -> [STT module] -> text -> [Website displays text]
                                          -> [THIS MODULE: TTS] -> user hears it back
                                          -> (if user confirms) -> [Backend]

Two engines are supported:
    1. OFFLINE  -> pyttsx3   (no internet needed, works instantly, robotic-ish voice)
    2. ONLINE   -> gTTS      (needs internet, Google's voice, sounds more natural)

Both are wrapped behind the SAME interface (TextToSpeech class) so you can
swap engines without changing the rest of your code.
"""

import os
import tempfile


class TextToSpeech:
    def __init__(self, engine="offline", rate=150, volume=1.0, voice_lang="en"):
        """
        engine     : if offline-pyttsx3 or if online-gTTS
        rate       : speaking speed 
        volume     : 0.0 to 1.0 (offline engine only)
        voice_lang : language code -"en" for english 
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

    #Bot speaks immediately and user rehear on the spot 
    def speak(self, text: str):
        
        #Converts text to speech and plays it immediately through the speakers.
        
        if not text or not text.strip():
            raise ValueError("No text provided to speak.")
        
        #for offline engine
        if self.engine_type == "offline":
            self.engine.say(text)
            self.engine.runAndWait()
        else:
            # online engine
            path = self.save(text)
            self._play_audio_file(path)
            os.remove(path)

    #Save to a file to send to backend
    def save(self, text: str, filename: str = None) -> str:
        """
        Converts tts and saves it as an audio file.
        Returns the file path and attach it to backend request
        or feed backs in STT module for testing.

        filename: if you don't give one, a temp .mp3/.wav is created for you.
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

    #play any audio file 
    # 
    # used by online engine 
    def _play_audio_file(self, path: str):
        from playsound import playsound
        playsound(path)

    def _temp_path(self, ext: str) -> str:
        fd, path = tempfile.mkstemp(suffix=ext)
        os.close(fd)
        return path



# STT -> website -> backend flow

if __name__ == "__main__":
    recognized_text = "This is the text that came from the speech to text module."

    tts = TextToSpeech(engine="offline")   # switch to "online" if you want gTTS

    # user will rehear 
    tts.speak(recognized_text)

    #Save the confirmed text as audio too, in case the backend
    # expects an audio file with the transcript
    audio_path = tts.save(recognized_text, filename="confirmed_output.wav")
    print(f"Saved audio for backend at: {audio_path}")

   