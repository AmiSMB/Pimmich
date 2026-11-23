import sys
import time
import re
from polib import pofile
from deep_translator import GoogleTranslator

def protect_placeholders(text):
    """
    Remplace les placeholders par des balises non traduisibles.
    Replace placeholders with tags that should not be translated.
    """
    placeholders = re.findall(r'%\([a-zA-Z0-9_]+\)s|%s|%d|%%', text)
    protected_text = text
    for i, p in enumerate(placeholders):
        protected_text = protected_text.replace(p, f'<span class="notranslate">{i}</span>', 1)
    return protected_text, placeholders

def restore_placeholders(text, placeholders):
    """
    Restaure les placeholders originaux.
    Restore the original placeholders.
    """
    for i, p in enumerate(placeholders):
        text = re.sub(r'<span class="notranslate">\s*' + str(i) + r'\s*</span>', p, text, 1)
    return text

def translate_po_file(file_path, target_lang):
    """
    Traduit les entrées non traduites dans un fichier .po en utilisant Google Translate.
    Translate untranslated entries in a .po file using Google Translate.
    """
    try:
        po = pofile(file_path)
        untranslated_entries = [e for e in po if not e.obsolete and not e.translated()]
        
        if not untranslated_entries:
            print(f"✅ No new entries to translate in {file_path}.")
            return

        print(f"Found {len(untranslated_entries)} entries to translate into '{target_lang}'...")

        translator = GoogleTranslator(source='auto', target=target_lang)
        consecutive_rate_limits = 0
        for i, entry in enumerate(untranslated_entries):
            try:
                # Protéger les placeholders
                # Protect placeholders.
                protected_text, placeholders = protect_placeholders(entry.msgid)
                
                # Traduire le texte protégé
                # Translate the protected text.
                translated_protected_text = translator.translate(protected_text)
                
                # Restaurer les placeholders
                # Restore the placeholders.
                final_translated_text = restore_placeholders(translated_protected_text, placeholders)
                
                # Supprimer le flag 'fuzzy' si présent pour forcer l'affichage
                # Remove the 'fuzzy' flag so the translation is used.
                if 'fuzzy' in entry.flags:
                    entry.flags.remove('fuzzy')
                
                entry.msgstr = final_translated_text
                consecutive_rate_limits = 0
                print(f"  ({i+1}/{len(untranslated_entries)}) '{entry.msgid[:30]}...' -> '{final_translated_text[:30]}...'")
                time.sleep(0.5)  # Délai pour respecter l'API
                # Respect the API rate limit.
            except Exception as e:
                print(f"  ❌ Could not translate entry '{entry.msgid}'. Error: {e}")
                if 'too many requests' in str(e).lower():
                    consecutive_rate_limits += 1
                    if consecutive_rate_limits >= 3:
                        print("⏸️ Translation paused after repeated rate limits. Successful translations have been kept.")
                        break
                    time.sleep(5.0)
                else:
                    time.sleep(0.5)

        print(f"Saving translated catalog to {file_path}...")
        po.save()
        print("✅ Translation complete.")

    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python utils/translate_po.py <path_to_messages.po> <target_language_code>")
        print("Example: python utils/translate_po.py translations/es/LC_MESSAGES/messages.po es")
        sys.exit(1)
        
    po_file_path = sys.argv[1]
    lang_code = sys.argv[2]
    
    translate_po_file(po_file_path, lang_code)
