#!/usr/bin/env bash
# 重生穿越系列封面 v2：作者=独孤元景，番茄规格 600x800
# 生成时用 768x1024（干净 3:4，FLUX 友好），随后 Pillow 缩放到精确 600x800。
set -u
cd /data/openclaw/workspace/story-studio
OUT="series/重生穿越/covers_v2"
mkdir -p "$OUT"

gen () {
  local title="$1" sub="$2" seed="$3" prompt="$4"
  echo "=================== $title ==================="
  timeout 500 python3 tools/book_cover_comfy.py \
    --title "$title" --subtitle "$sub" --author "独孤元景 著" \
    --prompt "$prompt" --output-dir "$OUT" --title-layout horizontal \
    --seed "$seed" --width 768 --height 1024 2>&1 | tail -2
}

NEG="completely blank empty space at top third and bottom, absolutely no text anywhere, no letters, no characters, no readable text, no fake letters, no signage, no watermark, no logo"

gen "汉末谋主" "一万破百万，我辅佐曹操定乾坤" 101 \
"Book cover, premium novel cover artwork, cinematic Chinese historical fiction, late Han dynasty warlords era, vast yellow loess battlefield at dusk, silhouettes of ancient cavalry charging through dust, torn war banners, distant burning city, solemn heroic epic mood, centered composition, $NEG, dramatic cinematic lighting, high detail, painterly realistic illustration, professional publishing cover design, deep bronze, ink black, dark red and muted gold color palette"

gen "崖山不亡" "十万军民蹈海前，我来守襄阳" 727 \
"Book cover, premium novel cover artwork, cinematic Chinese historical fiction, late Southern Song dynasty, lone besieged fortress city of Xiangyang by a vast misty river, distant Mongol cavalry and dust on the horizon, Song dynasty soldiers on the walls, tragic heroic last-stand mood, centered composition, $NEG, dramatic cinematic lighting, high detail, painterly realistic illustration, professional publishing cover design, ink blue, cold steel gray, dark gold and deep teal color palette"

gen "再造大明" "距煤山自缢还有两年，我来救崇祯" 203 \
"Book cover, premium novel cover artwork, cinematic Chinese historical fiction, late Ming dynasty Chongzhen era, snowy Forbidden City palace at night, tattered imperial dragon banner in wind, a lone official silhouette facing the palace, somber doomed-empire mood, centered composition, $NEG, dramatic cinematic lighting, high detail, painterly realistic illustration, professional publishing cover design, pale gray, snow white, ink black and muted imperial gold color palette"

gen "长安将倾" "我知道，安史之乱明年就来" 204 \
"Book cover, premium novel cover artwork, cinematic Chinese historical fiction, prosperous High Tang dynasty Chang'an, grand Tang city gate and palace towers at golden dusk, silk road camel caravan silhouettes, blooming peonies, prosperous yet ominous mood of coming disaster, centered composition, $NEG, dramatic cinematic lighting, high detail, painterly realistic illustration, professional publishing cover design, warm gold, vermilion red, imperial amber with looming dark clouds color palette"

gen "刑徒封侯" "从长城苦役，到未央宫宰相" 205 \
"Book cover, premium novel cover artwork, cinematic Chinese historical fiction, end of Qin dynasty, the Great Wall winding like a dragon across mountains under gray sky, tiny laboring convict figures on the wall, distant grand Han palace hall contrast, epic rise-from-nothing mood, centered composition, $NEG, dramatic cinematic lighting, high detail, painterly realistic illustration, professional publishing cover design, bronze, earthen yellow, ink black and cold stone gray color palette"

gen "三国神医" "华佗之上，我在乱世救苍生" 206 \
"Book cover, premium novel cover artwork, cinematic Chinese historical fiction, Three Kingdoms era, a military field tent with medicine chest and silver acupuncture needles, distant battlefield with fire and warships on a river at night, healer silhouette, tense wartime healing mood, centered composition, $NEG, dramatic cinematic lighting, high detail, painterly realistic illustration, professional publishing cover design, deep crimson, ink green, dark bronze and warm lamplight color palette"

gen "洪武谋臣" "伴朱元璋如伴虎，我步步惊心" 207 \
"Book cover, premium novel cover artwork, cinematic Chinese historical fiction, early Ming dynasty Hongwu era, imperial palace hall with cold light through window lattice casting prison-bar shadows, a lone minister silhouette before a distant empty dragon throne, oppressive paranoid court mood, centered composition, $NEG, dramatic cinematic lighting, high detail, painterly realistic illustration, professional publishing cover design, cold gray, ink black, muted imperial gold and shadow color palette"

gen "靖康不耻" "经济学教授穿越北宋，富国更强国" 208 \
"Book cover, premium novel cover artwork, cinematic Chinese historical fiction, late Northern Song dynasty, prosperous Bianjing city partly in flames, Jin dynasty armored cavalry pressing at the gates, scattered account ledgers and counting rods motif, tension of empire on the brink, centered composition, $NEG, dramatic cinematic lighting, high detail, painterly realistic illustration, professional publishing cover design, ash gray, ink blue, dark red and cold bronze color palette"

gen "明末海枭" "红毛炮再远，也轰不塌我的战舰" 838 \
"Book cover, premium novel cover artwork, cinematic Chinese historical fiction, late Ming early Qing maritime era, a Chinese war junk with cannons firing in a fierce sea battle at dusk, a Dutch galleon burning in the distance, stormy ocean and fire glow, epic naval warfare mood, centered composition, $NEG, dramatic cinematic lighting, high detail, painterly realistic illustration, professional publishing cover design, deep navy blue, fire orange, dark teal and gunsmoke gray color palette"

gen "盛唐挂机" "现代睡一觉，古代已过四天" 210 \
"Book cover, premium novel cover artwork, cinematic Chinese historical fiction, High Tang dynasty countryside, peaceful farmland by the Wei river in early spring, budding willow trees and thin mist, a farmer figure with distant Chang'an city on the horizon, warm idyllic slice-of-life mood, centered composition, $NEG, soft golden hour lighting, high detail, painterly realistic illustration, professional publishing cover design, warm yellow, fresh green, soft amber and gentle blue color palette"

echo "=== 缩放到番茄规格 600x800 ==="
python3 - <<'PY'
from PIL import Image
import glob, os
outdir = "series/重生穿越/covers_v2"
final = "series/重生穿越/covers_final_600x800"
os.makedirs(final, exist_ok=True)
for f in sorted(glob.glob(os.path.join(outdir, "*_cover.png"))):
    img = Image.open(f).convert("RGB")
    img = img.resize((600, 800), Image.LANCZOS)
    # 用书名(文件名首段)命名
    base = os.path.basename(f).split("_")[0]
    out = os.path.join(final, f"{base}.jpg")
    img.save(out, "JPEG", quality=92)
    print(f"  {base}.jpg  ({os.path.getsize(out)//1024} KB)")
print("完成 →", final)
PY