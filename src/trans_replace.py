# ------------------------------------------------------------------------------
# 誤翻訳などを一括で置換するためのプログラム
# python3 trans_replace.py で実行する。RFC Transからは独立している。
# ------------------------------------------------------------------------------

import glob
import json

# 変換ルールの一覧
rules = {
    "Status of This Memo": "本备忘录的现状",
}

def trans_replace() -> None:
    for filename in glob.glob('data/*/rfc*-trans.json'):
        # print(filename)

        with open(filename, 'r', encoding="utf-8") as f:
            obj = json.load(f)

        is_changed = False
        for paragraph in obj['contents']:

            # 変換ルールに基づく置換
            for text_eng, text_zh in rules.items():
                if paragraph['text'] == text_eng:
                    paragraph['zh'] = text_zh
                    is_changed = True

            # セクション番号が「1.1。」となっている部分の修正
            # if paragraph.get('zh'):
            #     m = re.match(r'^(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)。(.*)$',
            #                  paragraph['zh'])
            #     if m:
            #         paragraph['zh'] = m[1] + '. ' + m[2]
            #         is_changed = True

        if is_changed:
            with open(filename, 'w', encoding="utf-8") as f:
                json.dump(obj, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    trans_replace()
