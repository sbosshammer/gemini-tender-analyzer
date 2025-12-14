import streamlit as st
from google import genai
import os
import io
import tempfile # <--- НОВЫЙ ИМПОРТ

# --- Konfiguration des API-Clients ---
# Единственный блок try/except для инициализации API
try:
    API_KEY = os.getenv("GEMINI_API_KEY") or st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=API_KEY)
except Exception:
    st.error("Fehler bei der Initialisierung des Gemini API. Bitte prüfen Sie den 'GEMINI_API_KEY' in den Streamlit Secrets.")
    st.stop()


def analyze_tender(files, user_prompt, tender_name="Aktuelle Ausschreibung"):
    """
    Lädt die Dokumente, сохраняя их локально для правильного определения MIME-типа,
    анализирует их с Gemini 1.5 Pro и затем удаляет.
    """
    uploaded_gemini_files = []
    
    st.info(f"Lade {len(files)} Dokumente in die Gemini File API hoch...")

    # 1. Hochladen der Dateien (Метод временного файла для обхода ошибки MIME-типа)
    for uploaded_file in files:
        temp_file = None
        try:
            # 1. Создание временного файла с правильным расширением
            # Используется для того, чтобы Python мог сам определить MIME-тип по расширению
            ext = uploaded_file.name.split('.')[-1]
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}')
            
            # 2. Запись содержимого Streamlit-файла во временный файл
            temp_file.write(uploaded_file.getvalue())
            temp_file.close()
            
            # 3. Загрузка файла в Gemini API по пути к файлу
            # Этот метод позволяет библиотеке Python автоматически определить MIME-тип
            file = client.files.upload(
                file=temp_file.name
            )
            
            uploaded_gemini_files.append(file)
            
        except Exception as e:
            st.error(f"Fehler beim Hochladen der Datei '{uploaded_file.name}': {type(e).__name__}: {e}")
        
        finally:
            # 4. Очистка временного локального файла
            if temp_file and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            
    
    if not uploaded_gemini_files:
        st.error("Keine Dateien konnten erfolgreich hochgeladen werden. Die Analyse wird abgebrochen.")
        return None
        
    st.success(f"✅ Dateien erfolgreich hochgeladen. Die Analyse beginnt...")

    # 2. Prompterstellung und Analyse
    full_prompt = f"""
AUSSCHREIBUNG: {tender_name}

Bitte analysieren Sie ALLE beigefügten Dokumente dieser Ausschreibung. 
Ihre Aufgabe ist es: {user_prompt}

Wichtig: 
1. Verwenden Sie NUR die hochgeladenen Dokumente als Quelle.
2. Extrahieren Sie nur präzise Daten und zitieren Sie bei Fakten die Quelle (Dateiname oder Dokumenttitel).
"""
    
    content = [full_prompt] + uploaded_gemini_files
    
    response = client.models.generate_content(
        model='gemini-2.5-flash', 
        contents=content
    )
    
    result_text = response.text

    # 3. Очистка
    st.info("Starte die Bereinigung (Löschen der temporären Dateien aus der Cloud)...")
    for file in uploaded_gemini_files:
        try:
            client.files.delete(name=file.name)
        except Exception:
            st.warning(f"Datei {file.name} konnte nicht gelöscht werden (Möglicherweise bereits gelöscht).")
    st.success("Bereinigung abgeschlossen. Der Kontext ist isoliert.")

    return result_text


# --- STREAMLIT BENUTZEROBERFLÄCHE (UI) ---

st.title("📄 KI-Analyse von Ausschreibungsunterlagen (Gemini)")
st.caption("Laden Sie alle Dokumente EINER Ausschreibung hoch, geben Sie Ihren Prompt ein und erhalten Sie eine strukturierte Analyse.")

# 1. Dateiupload-Feld
uploaded_files = st.file_uploader(
    "1. Laden Sie alle Dokumente der Ausschreibung hoch (Word, PDF, Excel usw.)",
    accept_multiple_files=True
)

# 2. Prompt-Eingabefeld
default_prompt = """
**Rolle:**
Du bist ein hochpräziser, streng regelbasierter KI-Assistent zur Analyse öffentlicher Ausschreibungsunterlagen. Du arbeitest ausschließlich mit dem Inhalt der bereitgestellten Dokumente.
Du verwendest kein Weltwissen, keine Muster, keine Branchenannahmen und keine Vermutungen.

**Ziel:**
Extrahiere die Inhalte zu den unten genannten Kriterien und präsentiere das Ergebnis in einer einzigen, sauberen **Markdown-Tabelle**.

**Zu analysierende Kriterien:**
1. Projektbeschreibung
2. Technologie
3. Unternehmensgröße/Umsatz
4. Zertifizierungen
5. Kompetenzen Schlüsselpersonal
6. Anzahl Schlüsselpersonal
7. Vor-Ort/Remote
8. Versicherungshöhe
9. Referenzen

**Wichtigste Arbeitsregeln (Anti-Halluzination):**
1. **Quellenbasis:** Verwende **ausschließlich** die beigefügten Dokumente.
2. **Standard-Ausgabe bei Fehlen:** Wenn eine Information **nicht explizit** vorhanden oder belegbar ist:
   → Gib in der Tabelle **"Keine Angabe"** aus.
3. **Клар Widerspruch:** Wenn sich Angaben widersprechen, gib **beide** Varianten an und markiere als **"Widerspruch"**. Triff keine Entscheidung.
4. **Spezialregeln:** Für *Unternehmensgröße/Umsatz*, *Versicherungshöhe* und *Referenzen* gilt: Nur **konkrete Zahlen/Beträge/Projekte** ausgeben. Allgemeine Phrasen führen zu **"Keine Angabe"**.
5. **Zertifizierungen:** Nur ausgeben, wenn **wortwörtlich** genannt und **eindeutig dem Anbieter zuordenbar**. Bei Unklarheit: **"Keine Angabe (unklare Zuordnung)"**.

**Ausgabeformat (Zwingend):**

Du musst das Ergebnis in einer einzigen Markdown-Tabelle mit exakt zwei Spalten zurückgeben (Kriterium und Ergebnis), **ohne** JSON или Code-Blöcke.

| Kriterium | Ergebnis (Dokumentnahe Wiedergabe) |
| :--- | :--- |
| Projektbeschreibung | [Extrahierter Text oder "Keine Angabe"] |
| Technologie | [Extrahierter Text oder "Keine Angabe"] |
| Unternehmensgröße/Umsatz | [Extrahierter Text oder "Keine Angabe"] |
| Zertifizierungen | [Extrahierter Text oder "Keine Angabe (unklare Zuordnung)"] |
| Kompetenzen Schlüsselpersonal | [Extrahierter Text oder "Keine Angabe"] |
| Anzahl Schlüsselpersonal | [Extrahierter Text oder "Keine Angabe"] |
| Vor-Ort/Remote | [Extrahierter Text или "Keine Angabe"] |
| Versicherungshöhe | [Extrahierter Text или "Keine Angabe"] |
| Referenzen | [Extrahierter Text или "Keine Angabe"] |
"""
user_prompt = st.text_area(
    "2. Ihr Prompt (Anweisungs-Template):", 
    value=default_prompt, 
    height=200
)

# 3. Analyse-Button
if uploaded_files and st.button("🚀 3. Analyse der Ausschreibung starten"):
    if not user_prompt:
        st.warning("Bitte geben Sie einen Prompt für die Analyse ein.")
    else:
        # Zeigt einen Lade-Spinner während der Verarbeitung
        with st.spinner('Verarbeite Dokumente und analysiere mit Gemini 1.5 Pro...'):
            result_text = analyze_tender(uploaded_files, user_prompt)

            if result_text:
                st.subheader("✅ Analyse-Ergebnis (Zum Kopieren bereit):")
                st.markdown(result_text) # Zeigt die formatierte Markdown-Tabelle
