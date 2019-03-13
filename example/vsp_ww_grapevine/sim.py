"""This is an example on running HydroShoot on a potted grapevine with a
simple shoot architecture.
"""

from os import getcwd

from openalea.mtg import traversal
from openalea.plantgl.all import Scene
from hydroshoot import architecture, display, model

# =============================================================================
# Construct the plant mock-up
# =============================================================================

# Path for plant digitalization data.
g = architecture.vine_mtg('digit.input')

# Local Coordinates Correction
for v in traversal.iter_mtg2(g, g.root):
    architecture.VinePhytoModular(g, v)
    architecture.VineAxeII(g, v, pruning_type='avg_field_model', N_max=6, insert_angle=90,
                           N_max_order=6)
    architecture.VinePetiole(g, v, pet_ins=90., pet_ins_cv=0., phyllo_angle=180.)
    architecture.VineLeaf(g, v, leaf_inc=-45., leaf_inc_cv=100., lim_max=12.5, lim_min=5.,
                          order_lim_max=5.5, max_order=55, rand_rot_angle=90.,
                          cordon_vector=None)
    architecture.VineMTGProp(g, v)
    architecture.VineMTGGeom(g, v)  # ,theta_1=90,theta_2=180,theta_2_cv=10.)
    architecture.VineTransform(g, v)

# Display of the plant mock-up (result in 'fig_01_plant_mock_up.png')
# scene = HSVisu.visu(g,def_elmnt_color_dict=True,scene=Scene(),
#                    snap_shot_path='mockup.png')
scene = display.visu(g, def_elmnt_color_dict=True, scene=Scene(),
                     view_result=True)

# =============================================================================
# Run HydroShoot
# =============================================================================

model.run(g, str(getcwd()) + '/', scene)
