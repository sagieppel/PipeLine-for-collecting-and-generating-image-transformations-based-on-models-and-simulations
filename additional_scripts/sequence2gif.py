import os
import cv2
import numpy as np
import imageio.v2 as imageio


import os
import cv2
import numpy as np
import imageio.v2 as imageio


def images_to_gif(folder, target_file, size=None, fps=10, loop=0):
    """
    Reads images named 0.jpg, 1.jpg, 2.jpg, ... from `folder`,
    optionally resizes them, and stacks them into an animated GIF.

    Args:
        folder (str): path to folder containing 0.jpg, 1.jpg, ...
        target_file (str): output .gif path
        size (tuple[int, int] | None): (width, height) to resize to.
                                        If None, keeps original size of first image.
        fps (int): frames per second for the gif
        loop (int): number of times to loop. 0 = infinite (default).
    """
    files = [f for f in os.listdir(folder) if f.lower().endswith(('.jpg', '.jpeg'))]

    valid_files = []
    for f in files:
        name, _ = os.path.splitext(f)
        if name.isdigit():
            valid_files.append(f)

    if not valid_files:
        raise ValueError(f"No numerically named jpg files found in {folder}")

    valid_files.sort(key=lambda f: int(os.path.splitext(f)[0]))

    frames = []
    target_size = size

    for fname in valid_files:
        path = os.path.join(folder, fname)
        img = cv2.imread(path, cv2.IMREAD_COLOR)

        if img is None:
            print(f"Warning: could not read {path}, skipping")
            continue

        if target_size is None:
            h, w = img.shape[:2]
            target_size = (w, h)

        img_resized = cv2.resize(img, target_size, interpolation=cv2.INTER_AREA)
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        frames.append(img_rgb)

    if not frames:
        raise ValueError("No valid frames were loaded, cannot create GIF")

    duration = 1.0 / fps
    imageio.mimsave(target_file, frames, duration=duration, loop=loop)
    print(f"Saved GIF with {len(frames)} frames to {target_file} (loop={loop})")
# Example usage:
# images_to_gif("frames_folder", "output.gif", size=(320, 240), fps=15)
########################################################################################################################################
import os
import cv2
import numpy as np


def images_to_strip(folder, target_file, size=None, gap=10, gap_color=(255, 255, 255)):
    """
    Reads images named 0.jpg, 1.jpg, 2.jpg, ... from `folder`,
    optionally resizes them, and stacks them horizontally side-by-side
    with a fixed pixel gap between them, saving the result as a single jpg.

    Args:
        folder (str): path to folder containing 0.jpg, 1.jpg, ...
        target_file (str): output .jpg path
        size (tuple[int, int] | None): (width, height) to resize each image to.
                                        If None, all images are resized to match
                                        the height of the first image (width scaled
                                        proportionally), so the row is well formed.
        gap (int): gap in pixels between consecutive images
        gap_color (tuple): BGR color of the gap strip (default white)
    """
    files = [f for f in os.listdir(folder) if f.lower().endswith(('.jpg', '.jpeg'))]

    valid_files = []
    for f in files:
        name, _ = os.path.splitext(f)
        if name.isdigit():
            valid_files.append(f)

    if not valid_files:
        raise ValueError(f"No numerically named jpg files found in {folder}")

    valid_files.sort(key=lambda f: int(os.path.splitext(f)[0]))  # 0.jpg, 1.jpg, ...

    imgs = []
    for fname in valid_files:
        path = os.path.join(folder, fname)
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            print(f"Warning: could not read {path}, skipping")
            continue
        imgs.append(img)

    if not imgs:
        raise ValueError("No valid images were loaded, cannot build strip")

    resized = []
    if size is not None:
        # explicit size given: resize every image to exactly that
        w, h = size
        for img in imgs:
            resized.append(cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA))
    else:
        # no size given: normalize to first image's height, keep aspect ratio
        target_h = imgs[0].shape[0]
        for img in imgs:
            h, w = img.shape[:2]
            scale = target_h / h
            new_w = int(round(w * scale))
            resized.append(cv2.resize(img, (new_w, target_h), interpolation=cv2.INTER_AREA))

    # build the gap column, matching the common height
    height = resized[0].shape[0]
    gap_col = np.full((height, gap, 3), gap_color, dtype=np.uint8)

    # interleave images and gap columns
    pieces = []
    for i, img in enumerate(resized):
        pieces.append(img)
        if i != len(resized) - 1:
            pieces.append(gap_col)

    strip = np.hstack(pieces)

    cv2.imwrite(target_file, strip)
    print(f"Saved strip image ({strip.shape[1]}x{strip.shape[0]}) with {len(resized)} frames to {target_file}")


# Example usage:
# images_to_strip("frames_folder", "output.jpg", size=(200, 200), gap=10)



################################################################################################################################################
# main_in_dir = r"/media/fogbrain/6TB/EmergenTexture_Full_Code/Transformation_ON_IMAGE_Rearange/single_img_transformation_large4"
# outdir = r"/media/fogbrain/6TB/EmergenTexture_Full_Code/gif_single_img_transformation_large4/"
# main_in_dir = r"/media/fogbrain/6TB/EmergenTexture_Full_Code/Transformation_ON_IMAGE_Rearange/img2img_transformation_large4"
# outdir = r"/media/fogbrain/6TB/EmergenTexture_Full_Code/gif_img2img_transformation_large4/"

# main_in_dir = r"/media/fogbrain/6TB/EmergenTexture_Full_Code/Transformation_ON_IMAGE_Rearange/img2img_transformation_large3"
# outdir = r"/media/fogbrain/6TB/EmergenTexture_Full_Code/gif_img2img_transformation_large3/"
# main_in_dir = r"/media/fogbrain/6TB/EmergenTexture_Full_Code/Transformation_ON_IMAGE_Rearange/img2img_transformation_small4"
# outdir = r"/media/fogbrain/6TB/EmergenTexture_Full_Code/gif_single_img_transformation_small4/"
main_in_dir = r"/media/fogbrain/6TB/EmergenTexture_Full_Code/Transformation_ON_IMAGE_Rearange/single_img_transformation_large3"
outdir = r"/media/fogbrain/6TB/EmergenTexture_Full_Code/gif_single_img_transformation_large3/"


if not os.path.exists(outdir): os.makedirs(outdir)

for ii,topic in enumerate(os.listdir(main_in_dir)):
    topic_dir = os.path.join(main_in_dir, topic)
    if not os.path.isdir(topic_dir): continue
#    if ii >30: continue
    outtopic_dir= outdir + "//"+topic
    if not os.path.exists(outtopic_dir): os.makedirs(outtopic_dir)
    for trans_name in os.listdir(topic_dir):
        trans_dir = os.path.join(topic_dir,trans_name)
        if not os.path.isdir(trans_dir): continue
        print(trans_dir +"\n----->\n"+ outdir+"/"+trans_name+".jpg")
        try:
          images_to_gif(trans_dir, outtopic_dir + "/" + trans_name + ".gif", fps=4)
         # images_to_strip(trans_dir, outdir+"/"+trans_name+".jpg", size=(200, 200), gap=10)
        except:
          continue

