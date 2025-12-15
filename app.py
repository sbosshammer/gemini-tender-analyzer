import streamlit as st
from google import genai
import os
import io
import tempfile 
import time # Hinzugefügt für die Sicherheit, aber nicht zwingend genutzt

# --- Initialisierung des Streamlit Session State (Sitzungsstatus) ---
# Wird zur Speicherung der Analyseergebnisse und zum Zurücksetzen des Upload-Feldes verwendet
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = []
if 'file_uploader_key' not in st.session_state:
    st.session_state.file_uploader_key = 0

# --- Bereinigungsfunktionen ---
def clear_file_uploader():
    """Setzt den Schlüssel des Datei-Upload-Feldes zurück, wodurch das UI zwangsweise geleert wird."""
    st.session_state["file_uploader_key"] += 1

# --- Konfiguration des API-Clients ---
# Der einzige try/except-Block für die API-Initialisierung
try:
    API_KEY = os.getenv("GEMINI_API_KEY") or st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=API_KEY)
except Exception:
    st.error("Fehler bei der Initialisierung des Gemini API. Bitte prüfen Sie den 'GEMINI_API_KEY' in den Streamlit Secrets.")
    st.stop()


# --- FUNKTION ZUR FINALEN ZUSAMMENFASSUNG ---
def summarize_results(client, results):
    """
    Fasst alle textuellen Analyseergebnisse zusammen und fordert Gemini zur finalen Konsolidierung auf.
    """
    if not results:
        return "Keine gespeicherten Ergebnisse zur Zusammenfassung vorhanden."

    # Fassen alle gespeicherten Tabellen in einem großen Text-Prompt zusammen
    all_results_text = "\n\n--- NÄCHSTES DOKUMENT FOLGT ---\n\n".join(results)
    
    # Prompt für die finale Konsolidierung
    consolidation_prompt = f"""
    Hochpräziser Assistent, bitte analysieren und konsolidieren Sie die Ergebnisse, die aus mehreren Ausschreibungsdokumenten stammen.
    
    Ihre Aufgabe:
    1. Fassen Sie alle Daten aus den unten stehenden Tabellen in **EINE finale Markdown-Tabelle** zusammen.
    2. Beseitigen Sie Duplikate.
    3. Bei widersprüchlichen Informationen geben Sie beide Versionen an oder wählen die vollständigere aus.
    4. Behalten Sie die gleiche Anzahl von Spalten bei (Kriterium und Ergebnis).

    Hier sind alle Ergebnisse:
    
    {all_results_text}
    """

    st.info("Sende alle Ergebnisse zur finalen Konsolidierung...")
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=consolidation_prompt
        )
        return response.text
    except Exception as e:
        return f"Kritischer Fehler bei der Zusammenfassung: {type(e).__name__}: {e}"


# --- FUNKTION ZUR ANALYSE EINES EINZELNEN DOKUMENTS ---
def analyze_tender(files, user_prompt, tender_name="Aktuelle Ausschreibung"):
    """
    Analysiert EIN Dokument.
    """
    uploaded_gemini_files = []
    
    # Zusätzliche Prüfung, ob der Client existiert
    if 'client' not in globals():
        st.error("API-Client wurde nicht initialisiert. Bitte prüfen Sie Ihren API-Schlüssel.")
        return None

    st.info(f"Lade {len(files)} Dokument(e) in die Gemini File API hoch...")

    # 1. Hochladen der Dateien (Temporäre Datei-Methode)
    for uploaded_file in files: # Im Zyklus wird nur eine Datei sein
        temp_file = None
        try:
            # 1. Erstellung einer temporären Datei mit der korrekten Endung
            ext = uploaded_file.name.split('.')[-1]
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}')
            
            # 2. Schreiben des Inhalts der Streamlit-Datei in die temporäre Datei
            temp_file.write(uploaded_file.getvalue())
            temp_file.close()
            
            # 3. Hochladen der Datei in die Gemini API über den Dateipfad
            file = client.files.upload(
                file=temp_file.name
            )
            
            uploaded_gemini_files.append(file)
            
        except Exception as e:
            st.error(f"Fehler beim Hochladen der Datei '{uploaded_file.name}': {type(e).__name__}: {e}")
        
        finally:
            # 4. Bereinigung der temporären lokalen Datei
            if temp_file and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            
    
    if not uploaded_gemini_files:
        st.error("Keine Dateien konnten erfolgreich hochgeladen werden. Die Analyse wird abgebrochen.")
        return None
        
    st.success(f"✅ Datei '{files[0].name}' erfolgreich hochgeladen. Die Analyse beginnt...")

    # 2. Prompt-Erstellung und Analyse
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

    # 3. Bereinigung (Löschen der temporären Dateien aus der Cloud)
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
    "1. Laden Sie EIN Dokument der Ausschreibung hoch (Word, PDF, Excel usw.)",
    accept_multiple_files=True,
    key=st.session_state.file_uploader_key # Anbindung an den Schlüssel zum Zurücksetzen
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
3. **Klarer Widerspruch:** Wenn sich Angaben widersprechen, gib **beide** Varianten an und markiere als **"Widerspruch"**. Triff keine Entscheidung.
4. **Spezialregeln:** Für *Unternehmensgröße/Umsatz*, *Versicherungshöhe* und *Referenzen* gilt: Nur **konkrete Zahlen/Beträge/Projekte** ausgeben. Allgemeine Phrasen führen zu **"Keine Angabe"**.
5. **Zertifizierungen:** Nur ausgeben, wenn **wortwörtlich** genannt und **eindeutig dem Anbieter zuordenbar**. Bei Unklarheit: **"Keine Angabe (unklare Zuordnung)"**.

**Ausgabeformat (Zwingend):**

Du musst das Ergebnis in einer einzigen Markdown-Tabelle mit exakt zwei Spalten zurückgeben (Kriterium und Ergebnis), **ohne** JSON oder Code-Blöcke.

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
    # Obligatorische Prüfung auf nur eine Datei
    elif len(uploaded_files) > 1: 
        st.error("Bitte laden Sie nur EIN Dokument zur Analyse pro Durchgang hoch, aufgrund der API-Kontextfenster-Einschränkungen.")
    else:
        # Zeigt einen Lade-Spinner während der Verarbeitung
        with st.spinner('Verarbeite Dokument und analysiere mit Gemini 2.5 Flash...'):
            result_text = analyze_tender(uploaded_files, user_prompt)

            if result_text:
                # Speichern des Analyseergebnisses im Sitzungsstatus
                st.session_state.analysis_results.append(result_text) 
                
                st.subheader("✅ Analyse-Ergebnis (Zum Kopieren bereit):")
                st.markdown(result_text)
                st.success(f"Ergebnis gespeichert. Gesamtzahl der Ergebnisse: {len(st.session_state.analysis_results)}")
                
                # Schaltfläche zum Leeren des Upload-Feldes nach erfolgreicher Analyse
                if st.button("Nächstes Dokument hochladen"):
                    clear_file_uploader()
                    st.rerun()

# --- 4. FINALE ZUSAMMENFASSUNG ---

if st.session_state.analysis_results:
    st.markdown("---")
    st.subheader(f"🔄 Gesammelte Ergebnisse: {len(st.session_state.analysis_results)} (zur Konsolidierung)")
    
    if st.button("⭐ 4. Finale Zusammenfassung erstellen"):
        with st.spinner('Fasse alle Ergebnisse in einer finalen Tabelle zusammen...'):
            # Übergabe des Clients, der zu Beginn initialisiert wurde
            final_summary = summarize_results(client, st.session_state.analysis_results)
            
            st.subheader("✅ Finaler konsolidierter Bericht:")
            st.markdown(final_summary)
            
            # Zusätzliche Schaltfläche zum Zurücksetzen des Zustands
            st.markdown("---")
            if st.button("Alle Ergebnisse löschen und neu starten"):
                st.session_state.analysis_results = []
                clear_file_uploader()
                st.rerun()
