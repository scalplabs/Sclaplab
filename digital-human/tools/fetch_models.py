"""Download the forced-alignment model (Apache-2.0) and CMUdict (BSD) used by server/speech."""
import os
import urllib.request

DST = os.environ.get("DH_W2V_DIR", os.path.expanduser("~/.cache/dh/w2v"))
CMU = os.environ.get("DH_CMUDICT", os.path.expanduser("~/.cache/dh/cmudict.dict"))
HF = "https://huggingface.co/facebook/wav2vec2-xlsr-53-espeak-cv-ft/resolve/main/"
os.makedirs(DST, exist_ok=True)
for f in ["config.json", "preprocessor_config.json", "special_tokens_map.json", "tokenizer_config.json", "vocab.json", "pytorch_model.bin"]:
    p = os.path.join(DST, f)
    if not os.path.exists(p):
        print("downloading", f)
        urllib.request.urlretrieve(HF + f, p)
if not os.path.exists(CMU):
    urllib.request.urlretrieve("https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict", CMU)
print("set DH_W2V_DIR=%s DH_CMUDICT=%s" % (DST, CMU))
