from pathlib import Path
TEXTS={'kh':{'welcome':'សូមស្វាគមន៍!','menu_download':'📥 ទាញយក','menu_how':'📘 របៀបប្រើ','menu_lang':'🌐 ភាសា','menu_usage':'📊 ការប្រើប្រាស់របស់ខ្ញុំ','menu_admin':'🛠 ផ្ទាំងគ្រប់គ្រង'},'en':{'welcome':'Welcome!','menu_download':'📥 Download','menu_how':'📘 How to Use','menu_lang':'🌐 Language','menu_usage':'📊 My Usage','menu_admin':'🛠 Admin Dashboard'}}
def t(lang,key,**kwargs):
    lang=lang if lang in TEXTS else 'kh'; return TEXTS[lang].get(key,key).format(**kwargs) if '{}' in TEXTS[lang].get(key,key) else TEXTS[lang].get(key,key)
