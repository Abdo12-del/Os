#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
الموقع = واجهة الدردشة. لا غير.

أمر المؤسس (2026-11-04): «احذف واجهة الوثائق أريد واجهة الدردشة».
فصار build_site ينسخ الـ messenger وحده إلى site/dist:

- على فيرسل (استضافة ثابتة): تفتح الجذر فتلقى الواجهة بوضع معاينة
  بعينة بيانات من المستودع — راية كهرمانية صادقة تقول ذلك.
- على جهازك: الخادم الحي ops/server.py يقدّم نفس الملفات على الجذر،
  بلا راية، ببياناتك وتدقيقك.

الوثائق لم تُفقد: بقيت markdown في المستودع (46 ملفًا) — مصدر الحقيقة،
تُقرأ من جتهاب مباشرة، وإن أردت واجهة لها يومًا تُسطر هنا من جديد.
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'site', 'dist')


def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)                 # لا بقايا لواجهة الوثائق المحذوفة
    os.makedirs(OUT)
    ops = os.path.join(ROOT, 'ops')
    shutil.copy(os.path.join(ops, 'chat.html'), os.path.join(OUT, 'index.html'))
    shutil.copy(os.path.join(ops, 'chat.html'), os.path.join(OUT, 'chat.html'))
    for f in ('chat.css', 'chat.js', 'mascot.png'):
        shutil.copy(os.path.join(ops, f), os.path.join(OUT, f))
    print('✅ واجهة الدردشة → site/dist/ (index.html) — الوثائق markdown '
          'في المستودع، بلا واجهة منشورة')
    return 0


if __name__ == '__main__':
    sys.exit(main())
