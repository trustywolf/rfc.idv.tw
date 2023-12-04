# ------------------------------------------------------------------------------
# RFCの文章を翻訳するプログラム
# ------------------------------------------------------------------------------

import deepl
from deepl.exceptions import (
    AuthorizationException,
    QuotaExceededException,
    TooManyRequestsException,
    ConnectionException,
)
import json
import os
import re
from tqdm import tqdm
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=+9), "JST")

env_auth_key = "DEEPL_AUTH_KEY"
env_server_url = "DEEPL_SERVER_URL"

# 変換元は必ず小文字で記載すること
trans_rules = {
    "abstract": "摘要",
    "introduction": "导言",
    "acknowledgement": "致谢",
    "acknowledgements": "致谢",
    "acknowledgments": "致谢",
    "status of this memo": "本备忘录的地位",  # '本文書の状態',
    "copyright notice": "版权声明",
    "table of contents": "目录",
    "author's address": "作者地址",
    "conventions": "公约",
    "terminology": "用语",
    "background": "背景",
    "discussion": "讨论",
    "security considerations": "安全考虑因素",
    "iana considerations": "IANA考虑因素",
    "references": "参考文献",
    "normative references": "规范性文献",
    "informative references": "参考性文献",
    "contributors": "贡献者",
    "uses": "用途",
    "specification": "规范",
    "where": "但是",
    "where:": "但是：",
    "assume:": "前提：",
    'the key words "must", "must not", "required", "shall", "shall not", "should", "should not", "recommended", "may", and "optional" in this document are to be interpreted as described in rfc 2119 [rfc2119].': '本文档中的关键词 "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", 以及 "OPTIONAL" 应按照RFC 2119 [RFC2119]中的描述进行解释。',
    'the key words "must", "must not", "required", "shall", "shall not", "should", "should not", "recommended", "not recommended", "may", and "optional" in this document are to be interpreted as described in bcp 14 [rfc2119] [rfc8174] when, and only when, they appear in all capitals, as shown here.': '本文档中的关键词 "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", 以及 "OPTIONAL" 应按照BCP 14 [RFC2119] [RFC8174]中描述的一样，当且仅当它们以全大写形式出现时进行解释。',
    "this document is subject to bcp 78 and the ietf trust's legal provisions relating to ietf documents (https://trustee.ietf.org/license-info) in effect on the date of publication of this document. please review these documents carefully, as they describe your rights and restrictions with respect to this document. code components extracted from this document must include simplified bsd license text as described in section 4.e of the trust legal provisions and are provided without warranty as described in the simplified bsd license.": "本文档受BCP 78以及本文档发布之日有效的IETF信托基金关于IETF文档的法律规定（https://trustee.ietf.org/license-info）的约束。 请仔细阅读这些文档，因为它们描述了您对本文档的权利和限制。 从本文档中提取的代码组件必须包含信托法律条款第 4.e 节中描述的简化 BSD 许可证文本，并且不提供简化 BSD 许可证中描述的担保。",
}


# 翻訳処理例外
class MyTranslateException(Exception):
    pass


# 翻訳抽象クラス
class Translator:
    def __init__(self, total, desc=""):
        self.count = 0
        self.total = total
        # プログレスバー
        bar_format = (
            "{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}{postfix}]"
        )
        self.bar = tqdm(total=total, desc=desc, bar_format=bar_format)

    def increment_progress(self, incr=1):
        # プログレスバー用の出力
        self.count += incr
        self.bar.update(incr)

    def output_progress(self, len, wait_time):
        # プログレスバーに詳細情報を追加
        self.bar.set_postfix(len=len, sleep=("%.1f" % wait_time))

    def close(self):
        return True


class TranslatorDeepL(Translator):
    # DeepL Python Library

    def __init__(self, total, desc=""):
        super(TranslatorDeepL, self).__init__(total, desc)

        auth_key = os.getenv(env_auth_key)
        server_url = os.getenv(env_server_url)
        if auth_key is None:
            raise Exception(
                f"Please provide authentication key via the {env_auth_key} "
                "environment variable or --auth_key argument"
            )

        # Create a DeepL translator object, and call get_usage() to validate connection
        deepl_translator: deepl.Translator = deepl.Translator(
            auth_key=auth_key, server_url=server_url, send_platform_info=False
        )
        u: deepl.Usage = deepl_translator.get_usage()
        self._limit_reached = u.any_limit_reached
        self._deepl_translator = deepl_translator

    def translate(self, text: str, dest="ZH") -> str:
        if len(text) == 0:
            return ""
        # 特定の用語については、翻訳ルール(trans_rules)で翻訳する
        zh = trans_rules.get(text.lower())
        if zh:
            return zh

        for i in range(0, 3):
            deepl_translator = self._deepl_translator
            wait_time = 0
            self.output_progress(len=len(text), wait_time=wait_time)  # プログレスバーに詳細情報を追加
            # 翻訳結果を取得する
            zh = deepl_translator.translate_text(
                text, source_lang="EN", target_lang=dest
            ).text

            # 翻訳結果が空文字のときはリトライする（最大3回）
            if re.match(r"^\s*$", zh):
                continue

            return zh

        # リトライしても翻訳結果が空文字のときは例外とする
        raise MyTranslateException(
            f"Translated text is empty string! input text: {text}"
        )

    def close(self):
        return True


def chunks(alist: list, n: int) -> list:
    for i in range(0, len(alist), n):
        yield alist[i : i + n]


def trans_rfc(rfc_number: int | str) -> bool:
    # 整数はRFC、文字列はDraft
    if type(rfc_number) is int:
        # 通常のRFCのとき
        input_dir = "data/%04d" % (rfc_number // 1000 % 10 * 1000)
        input_file = f"{input_dir}/rfc{rfc_number}.json"
        output_file = f"{input_dir}/rfc{rfc_number}-trans.json"
        midway_file = f"{input_dir}/rfc{rfc_number}-midway.json"
    elif m := re.match(r"draft-(?P<org>[^-]+)-(?P<wg>[^-]+)-(?P<name>.+)", rfc_number):
        # ドラフト版のRFCのとき
        organization = m["org"]
        working_group = m["wg"]
        rfc_draft_name = m["name"]
        input_dir = f"data/draft/{working_group}"
        input_file = (
            f"{input_dir}/draft-{organization}-{working_group}-{rfc_draft_name}.json"
        )
        output_file = f"{input_dir}/draft-{organization}-{working_group}-{rfc_draft_name}-trans.json"
        midway_file = f"{input_dir}/draft-{organization}-{working_group}-{rfc_draft_name}-midway.json"
    else:
        raise RuntimeError(f"fetch_rfc: Unknown format number={rfc_number}")

    if os.path.isfile(midway_file):  # 途中まで翻訳済みのファイルがあれば復元する
        with open(midway_file, "r", encoding="utf-8") as f:
            obj = json.load(f)
    else:
        with open(input_file, "r", encoding="utf-8") as f:
            obj = json.load(f)

    translator = TranslatorDeepL(total=len(obj["contents"]), desc="RFC %s" % rfc_number)
    is_canceled = False

    try:
        # タイトルの翻訳
        if not obj["title"].get("zh"):
            titles = obj["title"]["text"].split(" - ", 1)  # "RFC XXXX - Title"
            if len(titles) <= 1:
                obj["title"]["zh"] = "RFC %s" % rfc_number
            else:
                text = titles[1]
                zh = translator.translate(text)
                obj["title"]["zh"] = "RFC %s - %s" % (rfc_number, zh)

        # 段落の翻訳
        for i, obj_contents_i in enumerate(obj["contents"]):
            # 既に翻訳済みの段落はスキップする
            if obj_contents_i.get("zh"):
                translator.increment_progress()  # 進捗+1
                continue

            # 英語原文
            text = obj_contents_i["text"]
            # 英語原文の前文字（箇条書きの記号などを翻訳しないようにするため）
            pre_text = ""
            # 中国語翻訳文
            text_zh = ""

            # 箇条書きのパターン
            # 「-」「o」「*」「+」「$」「A.」「A.1.」「a)」「1)」「(a)」「(1)」「[1]」「[a]」「a.」
            pattern = r"^([\-o\*\+\$] |(?:[A-Z]\.)?(?:\d{1,2}\.)+(?:\d{1,2})? |\(?[0-9a-z]\) |\[[0-9a-z]{1,2}\] |[a-z]\. )(.*)$"

            if obj_contents_i.get("raw") is True:
                # 図表は翻訳しない
                pre_text, text = ("", "")
            elif m := re.match(pattern, text):
                # 記号的意味を持つ文字から始まる文は箇条書きなので、その前文字を除外して翻訳する。
                pre_text, text = m[1], m[2]
            elif m := re.match(r"^Appendix ([A-Z])\. (.*)$", text):
                # 原文がセクション付録の場合
                pre_text, text = (f"附录{m[1]}. ", m[2])
            else:
                # 通常の本文
                pre_text, text = ("", text)

            # 翻訳の実行
            text_zh = translator.translate(text)

            # 翻訳結果を格納
            obj["contents"][i]["zh"] = pre_text + text_zh

            translator.increment_progress()  # 進捗+1

        print("", flush=True)

        # 正常終了した時
        # 翻訳成果物をファイルに出力する
        with open(output_file, "w", encoding="utf-8", newline="\n") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            print(f"[+] Save file: {output_file}")
        # 不要な入力ファイルの削除
        os.remove(input_file)
        print(f"[+] Delete file: {input_file}")
        # 不要な中間ファイルの削除
        if os.path.isfile(midway_file):
            os.remove(midway_file)
            print(f"[+] Delete file: {midway_file}")
        return True

    except (
        AuthorizationException,
        QuotaExceededException,
        TooManyRequestsException,
        ConnectionException,
        MyTranslateException,
        KeyboardInterrupt,
    ) as e:
        # NoSuchElementException: Google翻訳で別のページが返ってきたときに発生する例外
        # TimeoutException: ネットワークなどの問題で発生する例外
        # WebDriverException: メモリ不足などでWebDriverがエラーしたとき
        # KeyboardInterrupt: ユーザが意図的に処理を停止したときに発生する例外
        print(f"[-] Translator Error! ({datetime.now(JST)})")
        print(f"[-] error={e}")

        # 異常終了した時
        # 途中まで翻訳済みのファイルを生成する
        with open(midway_file, "w", encoding="utf-8", newline="\n") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            print(f"[+] Save file: {midway_file}")
        # 例外をそのまま投げる
        raise

    finally:
        translator.close()


def trans_test() -> bool:
    translator = TranslatorDeepL(total=1)
    zh = translator.translate("test sample.", dest="ZH")
    print("[+] result:", zh)


if __name__ == "__main__":
    trans_test()
