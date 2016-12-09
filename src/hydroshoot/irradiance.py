# -*- coding: utf-8 -*-
"""
@author: Rami ALBASHA

Irradiance module of HydroShoot: an interface of the Caribu module.

TODO: plug to the standard interface of Caribu module.

This module computes leaf (and eventually other elements) interception and
absorption of incident irradiance.
given plant shoot.
"""

from numpy import array, deg2rad
from pandas import date_range
from copy import deepcopy
from pytz import timezone, utc
from pvlib.solarposition import ephemeris

from openalea.plantgl.all import Translated,Sphere,Shape,Material,Color3,Viewer
from alinea.caribu.sky_tools.spitters_horaire import RdRsH
from alinea.caribu.sky_tools import turtle, Gensun, GetLightsSun
from alinea.caribu.CaribuScene import CaribuScene

from hydroshoot.architecture import vector_rotation


def local2solar(local_time, latitude, longitude, tzone, temperature=25.):
    """
    Returns UTC time and Solar time in decimal hours (solar noon is 12.00),
    based on `pvlib.solarposition.ephemeris` function.

    :Parameters:
    - **local_time**: local (legal) time, given as a `datetime.time`-like object
    - **latitude** and **longitude**: float, given in degrees
    - **tzone**,: string, a legal 'pytz.timezone' (e.g. 'Europe/Paris')
    - **temperature** float, is given in degrees
    """
    time_zone = timezone(tzone)
    local_time = time_zone.localize(local_time)
    dateUTC = local_time.astimezone(utc)
    #hUTC = dateUTC.time()
    #DOYUTC = dateUTC.timetuple().tm_yday
    datet = date_range(local_time, local_time)
    LST = ephemeris(datet, latitude, longitude, temperature).solar_time.values[0]

    return dateUTC, LST


def opticals(mtg,leaf_lbl_prefix='L', stem_lbl_prefix=('in', 'Pet', 'cx'),
         wave_band='SW',
         opt_prop={'SW':{'leaf':(0.06,0.07),'stem':(0.13,),'other':(0.65,0.0)},
                'LW':{'leaf':(0.04,0.07),'stem':(0.13,),'other':(0.65,0.0)}}):
    """
    Attaches optical properties to elements of an MTG. An element may be a leaf,
    a stem, or 'other' when scene background elements (e.g. oculting objects)
    are attached to the MTG.

    :Parameters:
    - **mtg**: an MTG object
    - **leaf_lbl_prefix**, **stem_lbl_prefix**: string, the prefices of the leaf label and stem label, resp.
    - **wave_band**: string, wave band name, default values are 'SW' for *short wave band* or 'LS' for *long wave band*
    - **opt_prop**: the optical properties of mtg elements, given as a {band_name: material} dictionary of tuples (See :func:`CaribuScene.__init__` for more information).
    """

    leaf_material, stem_material = [opt_prop[wave_band][ikey] for ikey in ('leaf', 'stem')]
    other_material = opt_prop[wave_band]['other']

    geom = mtg.property('geometry')

    for vid in geom:
        n = mtg.node(vid)
        if n.label.startswith(leaf_lbl_prefix):
            n.opticals = leaf_material
        elif n.label.startswith(stem_lbl_prefix):
            n.opticals = stem_material
        elif n.label.startswith('other'):
            n.opticals = other_material

    return mtg


def irradiance_distribution(meteo, geo_location, E_type, tzone='Europe/Paris',
                     turtle_sectors='46', turtle_format='soc', sun2scene=None,
                     rotation_angle=0.):
    """
    Calculates energy distribution over a semi-hemisphere surrounding the plant [umol m-2 s-1].

    :Parameters:
    - **meteo**: the meteo data, given as `pandas.DataFrame`, expected columns are:
        - **time**: UTC time, given as a `datetime.time`-like object
        - **Tac**: float, air temperature [degrees]
        - **hs**:  float, air relative humidity (%)
        - **Rg** or **PPFD**: float, respectively global [W m-2] or photosynthetic photon flux density [umol m-2 s-1]
        - **u**: float, wind speed
        - **Ca**:  float, air CO2 concentration [ppm]
        - **Pa**: float, atmospheric pressure [kPa]
    - **geo_location**: a tuple of (latitude, longitude, elevation) given in degrees
    - **E_type**: string, one of the following 'Rg_Watt/m2', 'RgPAR_Watt/m2' or 'PPFD_umol/m2/s'
    - **tzone**= a `pytz.timezone` object
    - **turtle_sectors**, **turtle_format**: string, see :func:`turtle` from `sky_tools` package
    - **sun2scene**: takes None as default, otherwise, if a pgl.scene is provided, a sun object (sphere) is added to it
    - **rotation_angle**: float, counter clockwise azimuth between the default X-axis direction (South) and real direction of X-axis [degrees]

    :Returns:
    - **source_cum** a tuple of tuples, giving energy unit and sky coordinates

    :Notice:
    The meteo data can consiste of only one line (single event) or multiple lines.
    In the latter case, this function returns accumulated irradiance throughtout the entire periode with sun positions corresponding to each time step.

    TODO: replace by the icosphere procedure
    """

    for i, date in enumerate(meteo.time):

        if E_type.split('_')[0] == 'PPFD':
            energy = meteo['PPFD'][date]
        else:
            try:
                energy = meteo['Rg'][date]
            except:
                raise TypeError ("E_type must be one of the following 'Rg_Watt/m2', 'RgPAR_Watt/m2' or'PPFD_umol/m2/s'.")

        if len(meteo.time)==1 or energy !=0:

#           Convert irradiance to W m-2 (Spitters method always gets energy flux as Rg Watt m-2)
            if E_type == 'Rg_Watt/m2':
                corr = 1.
            elif E_type == 'RgPAR_Watt/m2':
                corr = 1./0.48
            elif E_type == 'PPFD_umol/m2/s':
                corr = 1./(0.48 * 4.6)
            else:
                raise TypeError ("E_type must be one of the following 'Rg_Watt/m2', 'RgPAR_Watt/m2' or'PPFD_umol/m2/s'.")

            energy = energy*corr

#           Convert to UTC datetime
            latitude, longitude, elevation = [geo_location[x] for x in range(3)]
            temperature = meteo.Tac.values[0]
            dateUTC, LST = local2solar(date, latitude, longitude, tzone, temperature)
            DOYUTC = dateUTC.timetuple().tm_yday
            hUTC = dateUTC.hour + dateUTC.minute/60.
            RdRsH_ratio = RdRsH(energy, DOYUTC, hUTC, latitude) # R: Attention, ne renvoie pas exactement le même RdRsH que celui du noeud 'spitters_horaire' dans topvine.

#           Third and final correction: it is always desirable to get energy as PPFD
            energy = energy*(0.48 * 4.6)

            R_diff = RdRsH_ratio*energy
            R_direct = (1-RdRsH_ratio)*energy

#           diffuse radiation
            energy, emission, direction, elevation, azimuth = turtle.turtle(sectors=turtle_sectors,format=turtle_format,energy=R_diff)
            sky=zip(energy,direction)

#           direct radiation
            sun=Gensun.Gensun()(Rsun=R_direct,DOY=DOYUTC,heureTU=hUTC,lat=latitude)
            sun=GetLightsSun.GetLightsSun(sun)
            sun_data=[(float(sun.split()[0]),(float(sun.split()[1]),float(sun.split()[2]),float(sun.split()[3])))]

#           diffuse radiation (distributed over a dome) + direct radiation (localized as a supplemental source)
            source=sky.__add__(sun_data)

            if i == 0:
                source_cum = []
                for line in range(len(source)):
                    source_cum.append([source[line][0], source[line][1]])

            else:
                for j in range(len(source)-1):
                    source_cum[j][0] += source[j][0]
                source_cum.append(source[-1])

            if i == len(meteo.time) - 1:
                for line in range(int(turtle_sectors)):
                    source_cum[line] = tuple(source_cum[line])

#           Rotate irradiance sources to cope with plant row orientation
            if rotation_angle != 0.:
                v_energy = [vec[0] for vec in source_cum]
                v_coord = [tuple(vector_rotation(vec[1],(0.,0.,1.), deg2rad(rotation_angle))) for vec in source_cum]
                source_cum = zip(v_energy, v_coord)

#           Add Sun to an existing pgl.scene
            if sun2scene != None:
                xSun,ySun,zSun = -500.*array([source_cum[-1][1][i] for i in range(3)])
                if zSun >= 0:
                    ss = Translated(xSun,ySun,zSun, Sphere(20))
                    sun = Shape(ss, Material('yellow', Color3(255,255,0)))
                    sun2scene.add(sun)
                Viewer.display(sun2scene)

    return source_cum


def hsCaribu(mtg, meteo, local_date, geo_location, E_type, unit_scene_length,
               tzone='Europe/Paris', wave_band='SW', source = None, direct=True,
               infinite=False,
               nz=50, dz=5, ds=50, pattern=False, turtle_sectors='46',
               turtle_format='soc',leaf_lbl_prefix='L', stem_lbl_prefix=('in', 'Pet', 'cx'),
               opt_prop={'SW':{'leaf':(0.06,0.07),'stem':(0.13,),'other':(0.06,0.07)},
                'LW':{'leaf':(0.04,0.07),'stem':(0.13,),'other':(0.06,0.07)}},
                rotation_angle = 0.):
    """
    Estimates intercepted energy by the plant canopy.

    :Parameters:
    - **mtg**: an MTG object
    - **meteo**: the meteo data, given as `pandas.DataFrame`, expected columns are:
        - **time**: UTC time, given as a `datetime.time`-like object
        - **Tac**: float, air temperature [degrees]
        - **hs**:  float, air relative humidity (%)
        - **Rg** or **PPFD**: float, respectively global [W m-2] or photosynthetic photon flux density [umol m-2 s-1]
        - **u**: float, wind speed
        - **Ca**:  float, air CO2 concentration [ppm]
        - **Pa**: float, atmospheric pressure [kPa]
    - **local_date**: a `datetime.datetime` object giving local (legal) time
    - **geo_location**: a tuple of (latitude, longitude, elevation) given in degrees
    - **E_type**: string, one of the following 'Rg_Watt/m2', 'RgPAR_Watt/m2' or 'PPFD_umol/m2/s'
    - **unit_scene_length**: the unit of length used for scene coordinate and for pattern (should be one of `CaribuScene.units` default)
    - **tzone**= a `pytz.timezone` object
    - **wave_band**: either 'SW' for *short wave band* or 'LS' for *long wave band*
    - **source**: a tuple of tuples, giving energy unit and sky coordinates, if None, this function calculates energy for a single given `date`
    - **direct**, **nz**, **dz**, **ds**, **pattern**: See :func:`runCaribu` from `CaribuScene` package
    - **turtle_sectors**, **turtle_format**: string, see :func:`turtle` from `sky_tools` package
    - **leaf_lbl_prefix**, **stem_lbl_prefix**: the prefices of the leaf label and stem label, resp.
    - **opt_prop**: the optical properties of mtg elements, given as a {band_name: material} dictionary of tuples (See :func:`CaribuScene.__init__` for more information)
    - **rotation_angle**: float, counter clockwise azimuth between the default X-axis direction (South) and real direction of X-axis [degrees]

    :Returns:
    - the mtg object, with the incident radiation (`Ei`) and absorbed radiation (`Eabs`), both in [umol m-2 s-1], attached to mtg vertices as properties.

    :Notice 1:
    **Ei** and **Eabs** units are returned in [umol m-2 s-1] **REGARDLESS** of the `unit_scence_length` type.

    :Notice 2:
    The meteo data can consiste of only one line (single event) or multiple lines.
    In the latter case, this function returns accumulated irradiance throughtout the entire periode with sun positions corresponding to each time step.
    """

    if source == None:
        if E_type.split('_')[0] == 'PPFD':
            energy = meteo['PPFD'].values[0]
        else:
            try:
                energy = meteo['Rg'].values[0]
            except:
                raise TypeError ("E_type must be one of the following 'Rg_Watt/m2', 'RgPAR_Watt/m2' or'PPFD_umol/m2/s'.")

        # First Correcting: Spitters method always gets energy flux as Rg Watt m-2
        if E_type == 'Rg_Watt/m2':
            corr = 1.
        elif E_type == 'RgPAR_Watt/m2':
            corr = 1./0.48
        elif E_type == 'PPFD_umol/m2/s':
            corr = 1./(0.48 * 4.6)
        else:
            raise TypeError ("E_type must be one of the following 'Rg_Watt/m2', 'RgPAR_Watt/m2' or'PPFD_umol/m2/s'.")

        energy = energy*corr

        latitude, longitude, elevation = [geo_location[x] for x in range(3)]
        temperature = meteo.Tac.values[0]
        dateUTC, LST = local2solar(local_date, latitude, longitude, tzone, temperature)
        DOYUTC = dateUTC.timetuple().tm_yday
        hUTC = dateUTC.hour + dateUTC.minute/60.
        RdRsH_ratio = RdRsH(energy, DOYUTC, hUTC, latitude) # R: Attention, ne renvoie pas exactement le même RdRsH que celui du noeud 'spitters_horaire' dans topvine.

    #   The new Caribu always gets energy per squared meter
    #    # Second correction: Caribu always gets energy flux per unit scene area
    #    if unit_scene_length == 'cm':
    #        corr2 = 1./10000.
    #        energy = energy*corr2

#       Convert irradiance to W m-2 (Spitters method always gets energy flux as Rg Watt m-2)
        energy = energy*(0.48 * 4.6)

        R_diff = RdRsH_ratio*energy
        R_direct = (1-RdRsH_ratio)*energy

#       diffuse radiation
        energy, emission, direction, elevation, azimuth = turtle.turtle(sectors=turtle_sectors,format=turtle_format,energy=R_diff)
        sky=zip(energy,direction)

#       direct radiation
        sun=Gensun.Gensun()(Rsun=R_direct,DOY=DOYUTC,heureTU=hUTC,lat=latitude)
        sun=GetLightsSun.GetLightsSun(sun)
        sun_data=[(float(sun.split()[0]),(float(sun.split()[1]),float(sun.split()[2]),float(sun.split()[3])))]

#       diffuse radiation (distributed over a dome) + direct radiation (localized as a supplemental source)
        source=sky.__add__(sun_data)

#       Rotate irradiance sources to cope with plant row orientation
        if rotation_angle != 0.:
            v_energy = [vec[0] for vec in source]
            v_coord = [tuple(vector_rotation(vec[1],(0.,0.,1.), deg2rad(rotation_angle))) for vec in source]
            source = zip(v_energy, v_coord)


#   Run caribu only if irradiance is greater that 0
    if sum([x[0] for x in source]) == 0.:
        mtg.properties()['Ei'] = {ikey:0. for ikey in mtg.property('geometry').keys()}
        mtg.properties()['Eabs'] = deepcopy(mtg.properties()['Ei'])
        caribu_scene = None
    else:
        # Attaching optical properties to each organ of the plant mock-up
        opticals = {wave_band: mtg.property('opticals')}

        # setup CaribuScene
        caribu_scene = CaribuScene(mtg, light=source, opt = opticals,
                                   soil_reflectance={wave_band:0.15},
                                    scene_unit=unit_scene_length,
                                    pattern=pattern)

        # run caribu
        raw, aggregated = caribu_scene.run(direct=direct, infinite=infinite, d_sphere=ds, layers=nz, split_face=False)

        # Getting the output as PPFD in umol m-2 s-1
        #for key in aggregated[wave_band]['Ei'].keys() : aggregated[wave_band]['Ei'][key] = aggregated[wave_band]['Ei'][key]/corr2
        #for key in aggregated[wave_band]['Eabs'].keys() : aggregated[wave_band]['Eabs'][key] = aggregated[wave_band]['Eabs'][key]/corr2

        # Attaching output to MTG
        mtg.properties()['Ei'] = aggregated[wave_band]['Ei']
        mtg.properties()['Eabs'] = aggregated[wave_band]['Eabs']

    return mtg, caribu_scene

#caribu_scene.plot(raw['SW']['Ei'])