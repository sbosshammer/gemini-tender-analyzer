import streamlit as st
from google import genai
import os
import io

# --- Konfiguration des API-Clients ---
# Der API-Schlüssel wird sicher über die Streamlit Secrets (oder Umgebungsvariable) geladen.
try:
    API_KEY = os.getenv("GEMINI_API_KEY") or st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=API_KEY)
except Exception:
    st.error("Fehler bei der Initialisierung des Gemini API. Bitte prüfen Sie den 'GEMINI_API_KEY' in den Streamlit Secrets.")
    st.stop()


def analyze_tender(files, user_prompt, tender_name="Aktuelle Ausschreibung"):
    """
    Lädt die Dokumente in die File API, analysiert sie mit Gemini 1.5 Pro und löscht sie.
    
    :param files: Liste der hochgeladenen Streamlit-Dateiobjekte.
    :param user_prompt: Der detaillierte Anweisungsprompt vom Benutzer.
    :param tender_name: Name der Ausschreibung.
    :return: Der generierte Analyse-Text von Gemini oder None bei Fehler.
    """
    uploaded_gemini_files = []
    
    st.info(f"Lade {len(files)} Dokumente in die Gemini File API hoch...")

    # 1. Hochladen der Dateien in die Gemini File API
    try:
        for uploaded_file in files:
            # 1. Считываем содержимое файла как байты
            file_bytes = uploaded_file.getvalue()
            
            # 2. Используем io.BytesIO, передавая только содержимое (самый чистый способ)
            file = client.files.upload(
                file=io.BytesIO(file_bytes) 
            )
            
            uploaded_gemini_files.append(file)
            
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
        
        # Inhalt für die API: Prompt-Text gefolgt von den Dateiobjekten
        contents = [full_prompt] + uploaded_gemini_files
        
        response = client.models.generate_content(
            model='gemini-1.5-pro', # Modell für den großen Kontextumfang (Context Window)
            contents=contents
        )
        
        return response.text

    except Exception as e:
        st.error(f"Ein kritischer Fehler ist bei der Analyse aufgetreten: {e}")
        return None
        
    finally:
        # 3. Reinigung (KRITISCHER ISOLATIONSSCHRITT)
        # Die hochgeladenen Dateien müssen nach der Verarbeitung gelöscht werden, 
        # um den Kontext zu isolieren und Speicherkosten zu vermeiden.
        st.info("Starte die Bereinigung (Löschen der temporären Dateien aus der Cloud)...")
        for file in uploaded_gemini_files:
            try:
                client.files.delete(name=file.name)
            except Exception as e:
                st.warning(f"Datei {file.name} konnte nicht gelöscht werden: {e}")
        st.success("Bereinigung abgeschlossen. Der Kontext ist isoliert.")


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
Du bist ein hochpräziser, streng regelbasierter KI-Assistent zur Analyse öffentlicher Ausschreibungsunterlagen. Deine Aufgabe ist es, **ausschließlich** die relevanten Daten aus den beigefügten Dokumenten zu extrahieren.

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
1. **Quellenbasis:** Verwende **ausschließlich** die beigefügten Dokumente als einzige Informationsquelle. Verbot von Weltwissen, Mustern, Annahmen und Vermutungen.
2. **Standard-Ausgabe bei Fehlen:** Wenn eine Information in den Dokumenten **nicht explizit** vorhanden, mehrdeutig oder nicht direkt belegbar ist:
   → Gib in der Tabelle **"Keine Angabe"** aus.
3. **Klarer Widerspruch:** Wenn sich Angaben innerhalb der Dokumente widersprechen, gib **beide** Varianten an und markiere diese klar als **"Widerspruch: [Text A] vs. [Text B]"**. Triff keine Wertung oder Entscheidung.
4. **Spezialregeln (Finanzielle/Allgemeine Kriterien):** Für Kriterien wie *Unternehmensgröße/Umsatz*, *Versicherungshöhe* und *Referenzen* gilt:
   * Gib nur **konkrete Zahlen**, **Beträge** oder **eindeutig beschriebene Projekte** aus.
   * Allgemeine Phrasen ("langjährige Erfahrung", "zahlreiche Kunden") gelten als **"Keine Angabe"**.
5. **Zertifizierungen:** Gib Zertifizierungen nur aus, wenn sie **wortwörtlich** genannt werden und **eindeutig dem Anbieter** zugeordnet werden müssen (nicht nur als Anforderung oder Produktmerkmal). Bei Unklarheit: **"Keine Angabe (unklare Zuordnung)"**.

**Ausgabeformat (Zwingend):**

Du musst das Ergebnis in einer einzigen Markdown-Tabelle mit exakt zwei Spalten zurückgeben (Kriterium und Ergebnis), **ohne** JSON, Code-Blöcke oder zusätzliche Erklärungen. Die Kriterien müssen genau in der oben genannten Reihenfolge erscheinen.

| Kriterium | Ergebnis (Dokumentnahe Wiedergabe) |
| :--- | :--- |
| Projektbeschreibung | [Extrahierter Text oder "Keine Angabe"] |
| Technologie | [Extrahierter Text oder "Keine Angabe"] |
| Unternehmensgröße/Umsatz | [Extrahierter Text oder "Keine Angabe"] |
| Zertifizierungen | [Extrahierter Text oder "Keine Angabe (unklare Zuordnung)"] |
| Kompetenzen Schlüsselpersonal | [Extrahierter Text oder "Keine Angabe"] |
| Anzahl Schlüsselpersonal | [Extrahierter Text oder "Keine Angabe"] |
| Vor-Ort/Remote | [Extrahierter Text oder "Keine Angabe"] |
| Versicherungshöhe | [Extrahierter Text oder "Keine Angabe"] |
| Referenzen | [Extrahierter Text oder "Keine Angabe"] |
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
                st.markdown(result_text) # Zeigt die formatierte Markdown-Tabelle oder JSON
                # Die Mitarbeiter können diesen Text nun kopieren und in ihre Excel-Tabelle einfügen.
