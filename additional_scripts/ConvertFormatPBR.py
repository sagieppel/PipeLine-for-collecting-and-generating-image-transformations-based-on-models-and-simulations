# Convert PBRs under transformation from sequence of image per channel (aka color,roughness) to sequence of PBRs 
import shutil
import os



in_dir = "PBR_im/"
out_dir = "PBR_single_im_conv"
if not os.path.exists(out_dir):
    os.mkdir(out_dir)

#######################################################################################
for dr in os.listdir(in_dir):
    in_path = os.path.join(in_dir,dr)
    out_path = os.path.join(out_dir, dr)
    if not os.path.exists(out_path): os.mkdir(out_path)
    print(in_path)
    for tpdr in os.listdir(in_path):
        in_sdir = os.path.join(in_path,tpdr)
        if os.path.isdir(in_sdir) and tpdr!= "Material_View":
               for ifl in os.listdir(in_sdir):
                    out_sdr = os.path.join(out_path,ifl[:-4])
                    if not os.path.exists(out_sdr):  os.mkdir(out_sdr)
                    shutil.move(in_sdir+"/"+ifl,out_sdr+"//"+tpdr+ifl[-4:])
                    print(in_sdir+"/"+ifl,out_sdr+"//"+tpdr+ifl[-4:])
