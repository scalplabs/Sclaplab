#!/usr/bin/env bash
# Fetch CC0 source data into $DH_EXT (default /home/user/work/ext) and HDRIs into $DH_HDRI.
set -euo pipefail
EXT=${DH_EXT:-/home/user/work/ext}; HDRI=${DH_HDRI:-/home/user/work/hdri}
mkdir -p "$EXT" "$HDRI"; cd "$EXT"
[ -d makehuman ] || git clone --depth 1 https://github.com/makehumancommunity/makehuman      # CC0 assets (base mesh, targets, rig, face units)
[ -d mpfb2 ] || git clone --depth 1 https://github.com/makehumancommunity/mpfb2              # CC0 rig json, region masks
if [ ! -d makehuman-py3-assets ]; then                                                       # MakeHuman 1.1 system assets (CC0) mirror
  GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/dmaugis/makehuman-py3-assets
  cd makehuman-py3-assets
  git lfs ls-files -n | grep -vE '^debug/|female|toon|afro|braid|ponytail|bob|long01|fedora|litspheres|old_|african' | \
    while read -r f; do curl -sfL -o "$f" "https://media.githubusercontent.com/media/dmaugis/makehuman-py3-assets/master/$f"; done
  cd ..
fi
for n in brown_photostudio_02 photo_studio_loft_hall kloofendal_48d_partly_cloudy_puresky cloudy_vondelpark hotel_room monochrome_studio_02; do
  [ -f "$HDRI/$n.exr" ] || curl -sfL -o "$HDRI/$n.exr" "https://huggingface.co/datasets/leodriesch/open-hdri-1k/resolve/main/data/polyhaven/$n/${n}_1k.exr"
done
echo done
