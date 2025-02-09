# Author: Sayantan Majumdar
# Email: smxnv@mst.edu

import geopandas as gpd
import pandas as pd
import rasterio as rio
import numpy as np
import subprocess
import fiona
import os
import multiprocessing
from joblib import Parallel, delayed
from glob import glob
from Python_Files.hydrolibs.sysops import make_gdal_sys_call_str, make_proper_dir_name
from shapely.geometry import Point

NO_DATA_VALUE = -32767.0


def reproject_vector(input_vector_file, outfile_path, ref_file, crs='epsg:4326', crs_from_file=True, raster=True):
    """
    Reproject a vector file
    :param input_vector_file: Input vector file path
    :param outfile_path: Output vector file path
    :param crs: Target CRS
    :param ref_file: Reference file (raster or vector) for obtaining target CRS
    :param crs_from_file: If true (default) read CRS from file (raster or vector)
    :param raster: If true (default) read CRS from raster else vector
    :return: Reprojected vector file in GeoPandas format
    """

    input_vector_file = gpd.read_file(input_vector_file)
    if crs_from_file:
        if raster:
            ref_file = rio.open(ref_file)
        else:
            ref_file = gpd.read_file(ref_file)
        crs = ref_file.crs
    else:
        crs = {'init': crs}
    output_vector_file = input_vector_file.to_crs(crs)
    output_vector_file.to_file(outfile_path)
    return output_vector_file


def clip_vector(input_shp_file, clip_file, output_shp_file, gdal_path='/usr/local/Cellar/gdal/2.4.2/bin/',
                extent_clip=True):
    """
    Clip an input vector using reference vector
    :param input_shp_file: Input shape file
    :param clip_file: Input clip file
    :param output_shp_file: Output shape file
    :param gdal_path: GDAL directory path, in Windows replace with OSGeo4W directory path, e.g. '/usr/bin/gdal/' on
    Linux or Mac and 'C:/OSGeo4W64/' on Windows, the '/' at the end is mandatory. Required only if extent_clip=False
    :param extent_clip: Clip using total extent of the shape file
    :return: None
    """

    if extent_clip:
        print('Clipping', input_shp_file)
        input_shp_file = gpd.read_file(input_shp_file)
        clip_file = gpd.read_file(clip_file)
        clipped_file = gpd.clip(input_shp_file, clip_file)
        clipped_file.to_file(output_shp_file)
    else:
        args = ['-clipsrc', clip_file, output_shp_file, input_shp_file]
        sys_call = make_gdal_sys_call_str(gdal_path=gdal_path, gdal_command='ogr2ogr', args=args)
        subprocess.call(sys_call)


def clip_vectors(input_vector_dir, clip_file, outdir, gdal_path='/usr/local/Cellar/gdal/2.4.2/bin/', extent_clip=True):
    """
    Clip all vectors in a directory
    :param input_vector_dir: Input directory containing shapefiles
    :param clip_file: Input Clip file
    :param outdir: Output directory
    :param gdal_path: GDAL directory path, in Windows replace with OSGeo4W directory path, e.g. '/usr/bin/gdal/' on
    Linux or Mac and 'C:/OSGeo4W64/' on Windows, the '/' at the end is mandatory. Required only if extent_clip=False
    :param extent_clip: Clip using total extent of the shape file
    :return: None
    """

    num_cores = multiprocessing.cpu_count()
    Parallel(n_jobs=num_cores)(delayed(parellel_vector_clip)(shp_file, clip_file=clip_file, outdir=outdir,
                                                             gdal_path=gdal_path, extent_clip=extent_clip)
                               for shp_file in glob(input_vector_dir + '*.shp'))


def parellel_vector_clip(shp_file, clip_file, outdir, gdal_path, extent_clip):
    """
    Use this from #clip_vectors to parallelize multiple vector clipping
    :param shp_file: Input shpfile
    :param clip_file: Input Clip file
    :param outdir: Output directory
    :param gdal_path: GDAL directory path, in Windows replace with OSGeo4W directory path, e.g. '/usr/bin/gdal/' on
    Linux or Mac and 'C:/OSGeo4W64/' on Windows, the '/' at the end is mandatory. Required only if extent_clip=False
    :param extent_clip: Clip using total extent of the shape file
    :return: None
    """

    out_shp = outdir + shp_file[shp_file.rfind(os.sep) + 1:]
    clip_vector(shp_file, clip_file, output_shp_file=out_shp, gdal_path=gdal_path, extent_clip=extent_clip)


def csv2shp(input_csv_file, outfile_path, delim=',', source_crs='epsg:4326', target_crs='epsg:4326',
            long_lat_pos=(7, 8)):
    """
    Convert CSV to Shapefile
    :param input_csv_file: Input CSV file path
    :param outfile_path: Output file path
    :param delim: CSV file delimeter
    :param source_crs: CRS of the source file
    :param target_crs: Target CRS
    :param long_lat_pos: Tuple containing positions of longitude and latitude columns respectively (zero indexing)
    :return: None
    """

    input_df = pd.read_csv(input_csv_file, delimiter=delim)
    input_df = input_df.dropna(axis=1)
    long, lat = input_df.columns[long_lat_pos[0]], input_df.columns[long_lat_pos[1]]
    geometry = [Point(xy) for xy in zip(input_df[long], input_df[lat])]
    gdf2shp(input_df, geometry, source_crs, target_crs, outfile_path)


def add_attribute_well_reg(input_well_reg_file, input_gw_csv_file, out_gw_shp_file, fill_attr='AF Pumped',
                           filter_attr='AMA', filter_attr_value='OUTSIDE OF AMA OR INA', use_only_ama_ina=False,
                           **kwargs):
    """
    Add an attribute present in the GW csv file to the Well Registry shape file based on matching ids given in kwargs.
    By default, the GW withdrawal is added. The csv ids must include: csv_well_id, csv_mov_id, csv_water_id,
    movement_type, water_type, The shp id must include shp_well_id. For the Arizona datasets, csv_well_id='Well Id',
    csv_mov_id='Movement Type', csv_water_id='Water Type', movement_type='WITHDRAWAL', water_type='GROUNDWATER', and
    shp_well_id='REGISTRY_I' by default. For changing, pass appropriate kwargs.
    :param input_well_reg_file: Input Well Registry shapefile
    :param input_gw_csv_file: Input GW csv file
    :param out_gw_shp_file: Output GWSI shapefile having GW withdrawal data
    :param fill_attr: Attribute present in the CSV file to add to Well Registry
    :param filter_attr: Remove specific wells based on this attribute. Set None to disable filtering.
    :param filter_attr_value: Value for filter_attr
    :param use_only_ama_ina: Set True to use only AMA/INA for model training
    :return: None
    """

    well_reg_gdf = gpd.read_file(input_well_reg_file)
    gw_df = pd.read_csv(input_gw_csv_file)
    csv_well_id = 'Well Id'
    csv_mov_id = 'Movement Type'
    csv_water_id = 'Water Type'
    movement_type = 'WITHDRAWAL'
    water_type = 'GROUNDWATER'
    shp_well_id = 'REGISTRY_I'
    if kwargs:
        csv_well_id = kwargs['csv_well_id']
        movement_type = kwargs['movement_type']
        water_type = kwargs['water_type']
        shp_well_id = kwargs['shp_well_id']
    if filter_attr:
        well_reg_gdf = well_reg_gdf[well_reg_gdf[filter_attr] != filter_attr_value]
    for csv_id in set(gw_df[csv_well_id]):
        sub_gw_df = gw_df[(gw_df[csv_well_id] == csv_id) & (gw_df[csv_mov_id] == movement_type) &
                          (gw_df[csv_water_id] == water_type)]
        if not sub_gw_df.empty:
            fill_value = list(sub_gw_df[fill_attr])
            if len(fill_value) > 1:
                fill_value = np.sum(fill_value)
            else:
                fill_value = fill_value[0]
            csv_id_modified = str(csv_id)
            if len(csv_id_modified) == 5:
                csv_id_modified = '0' + csv_id_modified
            well_reg_gdf.loc[well_reg_gdf[shp_well_id] == csv_id_modified, fill_attr] = fill_value
    if not use_only_ama_ina:
        well_reg_schema = fiona.open(input_well_reg_file).schema
        well_reg_schema['properties'][fill_attr] = 'float:24.20'
        well_reg_gdf.loc[well_reg_gdf['AMA'] == filter_attr_value, fill_attr] = -1e-16
        well_reg_gdf.loc[well_reg_gdf[fill_attr] == 0., fill_attr] = 1e-10
        well_reg_gdf.to_file(out_gw_shp_file, schema=well_reg_schema)
    else:
        well_reg_gdf.to_file(out_gw_shp_file)
    print(input_gw_csv_file, ': Matched wells:', well_reg_gdf.count()[shp_well_id])


def add_attribute_well_reg_multiple(input_well_reg_file, input_gw_csv_dir, out_gw_shp_dir, fill_attr='AF Pumped',
                                    filter_attr='AMA', filter_attr_value='OUTSIDE OF AMA OR INA',
                                    use_only_ama_ina=False, **kwargs):
    """
    Add an attribute present in the GW csv file to the Well Registry shape files (yearwise) based on matching ids given
    in kwargs. By default, the GW withdrawal is added. The csv ids must include: csv_well_id, csv_mov_id, csv_water_id,
    movement_type, water_type, The shp id must include shp_well_id. For the Arizona datasets, csv_well_id='Well Id',
    csv_mov_id='Movement Type', csv_water_id='Water Type', movement_type='WITHDRAWAL', water_type='GROUNDWATER', and
    shp_well_id='REGISTRY_I' by default. For changing, pass appropriate kwargs.
    :param input_well_reg_file: Input Well Registry shapefile
    :param input_gw_csv_dir: Input GW csv directory
    :param out_gw_shp_dir: Output Well Registry shapefile directory having GW withdrawal data
    :param fill_attr: Attribute present in the CSV file to add to Well Registry
    :param filter_attr: Remove specific wells based on this attribute. Set None to disable filtering.
    :param filter_attr_value: Value for filter_attr
    :param use_only_ama_ina: Set True to use only AMA/INA for model training
    :return: None
    """

    num_cores = multiprocessing.cpu_count() - 1
    print('Updating Well Registry shapefiles...\n')
    Parallel(n_jobs=num_cores - 1)(delayed(parallel_add_attribute_well_reg)(input_well_reg_file, input_gw_csv_file,
                                                                            out_gw_shp_dir, fill_attr, filter_attr,
                                                                            filter_attr_value, use_only_ama_ina,
                                                                            **kwargs)
                                   for input_gw_csv_file in glob(input_gw_csv_dir + '*.csv'))


def parallel_add_attribute_well_reg(input_well_reg_file, input_gw_csv_file, out_gw_shp_dir, fill_attr='AF Pumped',
                                    filter_attr='AMA', filter_attr_value='OUTSIDE OF AMA OR INA',
                                    use_only_ama_ina=False, **kwargs):
    """
    Add an attribute present in the GW csv file to the Well Registry shape files (yearwise) based on matching ids given
    in kwargs. By default, the GW withdrawal is added. The csv ids must include: csv_well_id, csv_mov_id, csv_water_id,
    movement_type, water_type, The shp id must include shp_well_id. For the Arizona datasets, csv_well_id='Well Id',
    csv_mov_id='Movement Type', csv_water_id='Water Type', movement_type='WITHDRAWAL', water_type='GROUNDWATER', and
    shp_well_id='REGISTRY_I' by default. For changing, pass appropriate kwargs. This function should be called from
    #add_attribute_well_reg_multiple(...)
    :param input_well_reg_file: Input well registry shapefile
    :param input_gw_csv_file: Input GW csv file
    :param out_gw_shp_dir: Output GWSI shapefile directory having GW withdrawal data
    :param fill_attr: Attribute present in the CSV file to add to Well Registry
    :param filter_attr: Remove specific wells based on this attribute. Set None to disable filtering.
    :param use_only_ama_ina: Set True to use only AMA/INA for model training
    :param filter_attr_value: Value for filter_attr
    :return: None
    """

    out_well_reg_file = out_gw_shp_dir + input_gw_csv_file[input_gw_csv_file.rfind(os.sep) + 1:
                                                           input_gw_csv_file.rfind('.')] + '.shp'
    add_attribute_well_reg(input_well_reg_file, input_gw_csv_file, out_well_reg_file, fill_attr, filter_attr,
                           filter_attr_value, use_only_ama_ina, **kwargs)


def gdf2shp(input_df, geometry, source_crs, target_crs, outfile_path):
    """
    Convert Geodatafarme to SHP
    :param input_df: Input geodataframe
    :param geometry: Geometry (Point) list
    :param source_crs: CRS of the source file
    :param target_crs: Target CRS
    :param outfile_path: Output file path
    :return:
    """

    crs = {'init': source_crs}
    gdf = gpd.GeoDataFrame(input_df, crs=crs, geometry=geometry)
    gdf.to_file(outfile_path)
    if target_crs != source_crs:
        reproject_vector(outfile_path, outfile_path=outfile_path, crs=target_crs, crs_from_file=False, ref_file=None)


def shp2raster(input_shp_file, outfile_path, value_field=None, value_field_pos=0, xres=1000., yres=1000., gridding=True,
               smoothing=4800, burn_value=None, add_value=True, gdal_path='/usr/local/Cellar/gdal/2.4.2/bin/'):
    """
    Convert Shapefile to Raster TIFF file
    :param input_shp_file: Input Shapefile path
    :param outfile_path: Output TIFF file path
    :param value_field: Name of the value attribute. Set None to use value_field_pos
    :param value_field_pos: Value field position (zero indexing)
    :param xres: Pixel width in geographic units
    :param yres: Pixel height in geographic units
    :param gridding: Set false to use gdal_rasterize (If gridding is True, the Inverse Distance Square algorithm used
    with default parameters)
    :param smoothing: Level of smoothing (higher values imply higher smoothing effect)
    :param burn_value: Set a fixed burn value instead of using value_field.
    :param add_value: Set False to disable adding value to existing raster cell
    :param gdal_path: GDAL directory path, in Windows replace with OSGeo4W directory path, e.g. '/usr/bin/gdal/' on
    Linux or Mac and 'C:/OSGeo4W64/' on Windows, the '/' at the end is mandatory
    :return: None
    """

    ext_pos = input_shp_file.rfind('.')
    sep_pos = input_shp_file.rfind(os.sep)
    if sep_pos == -1:
        sep_pos = input_shp_file.rfind('/')
    layer_name = input_shp_file[sep_pos + 1: ext_pos]
    shp_file = gpd.read_file(input_shp_file)
    if value_field is None:
        value_field = shp_file.columns[value_field_pos]
    minx, miny, maxx, maxy = shp_file.geometry.total_bounds
    no_data_value = NO_DATA_VALUE
    gdal_command = 'gdal_rasterize'
    if not gridding:
        args = ['-l', layer_name, '-a', value_field, '-tr', str(xres), str(yres), '-te', str(minx),
                str(miny), str(maxx), str(maxy), '-init', str(0.0), '-add', '-ot', 'Float32', '-of', 'GTiff',
                '-a_nodata', str(no_data_value), input_shp_file, outfile_path]
        if burn_value is not None:
            args = ['-l', layer_name, '-burn', str(burn_value), '-tr', str(xres), str(yres), '-te', str(minx),
                    str(miny), str(maxx), str(maxy), '-init', str(0.0), '-add', '-ot', 'Float32', '-of', 'GTiff',
                    '-a_nodata', str(no_data_value), input_shp_file, outfile_path]
        if not add_value:
            args = ['-l', layer_name, '-a', value_field, '-tr', str(xres), str(yres), '-te', str(minx),
                    str(miny), str(maxx), str(maxy), '-ot', 'Float32', '-of', 'GTiff', '-a_nodata', str(no_data_value),
                    input_shp_file, outfile_path]
    else:
        gdal_command = 'gdal_grid'
        xsize = np.int(np.round((maxx - minx) / xres))
        ysize = np.int(np.round((maxy - miny) / yres))
        args = ['-a', 'invdist:smoothing=' + str(smoothing) + ':nodata=' + str(no_data_value),
                '-zfield', value_field, '-l', layer_name, '-outsize', str(xsize), str(ysize), '-ot', 'Float32',
                '-of', 'GTiff', input_shp_file, outfile_path]
    sys_call = make_gdal_sys_call_str(gdal_path=gdal_path, gdal_command=gdal_command, args=args)
    subprocess.call(sys_call)


def csvs2shps(input_dir, output_dir, pattern='*.csv', target_crs='EPSG:4326', delim=',', long_lat_pos=(7, 8)):
    """
    Convert all CSV files present in a folder to corresponding Shapefiles
    :param input_dir: Input directory containing csv files which are named as <Layer_Name>_<Year>.[csv|txt]
    :param output_dir: Output directory
    :param pattern: CSV  file pattern
    :param target_crs: Target CRS
    :param delim: CSV file delimeter
    :param long_lat_pos: Tuple containing positions of longitude and latitude columns respectively (zero indexing)
    :return: None
    """

    for file in glob(input_dir + pattern):
        outfile_path = output_dir + file[file.rfind(os.sep) + 1: file.rfind('.') + 1] + 'shp'
        csv2shp(file, outfile_path=outfile_path, delim=delim, target_crs=target_crs, long_lat_pos=long_lat_pos)


def shps2rasters(input_dir, output_dir, burn_value=None, value_field=None, value_field_pos=0, xres=1000, yres=1000, gridding=True,
                 smoothing=4800, gdal_path='/usr/local/Cellar/gdal/2.4.2/bin/'):
    """
    Convert all shapefiles to corresponding TIFF files
    :param input_dir: Input directory containing Shapefiles which are named as <Layer_Name>_<Year>.shp
    :param output_dir: Output directory
    :param burn_value: Set a fixed burn value instead of using value_field.
    :param value_field: Name of the value attribute. Set None to use value_field_pos
    :param value_field_pos: Value field position (zero indexing)
    :param xres: Pixel width in geographic units
    :param yres: Pixel height in geographic units
    :param gridding: Set false to use gdal_rasterize (If gridding is True, the Inverse Distance Square algorithm used
    with default parameters)
    :param smoothing: Level of smoothing (higher values imply higher smoothing effect)
    :param gdal_path: GDAL directory path, in Windows replace with OSGeo4W directory path, e.g. '/usr/bin/gdal/' on
    Linux or Mac and 'C:/OSGeo4W64/' on Windows, the '/' at the end is mandatory
    :return: None
    """

    num_cores = multiprocessing.cpu_count() - 2
    Parallel(n_jobs=num_cores)(delayed(parallel_shp2raster)(shp_file, output_dir=output_dir, burn_value=burn_value,
                                                            value_field=value_field, value_field_pos=value_field_pos,
                                                            xres=xres, yres=yres, gdal_path=gdal_path,
                                                            gridding=gridding, smoothing=smoothing)
                               for shp_file in glob(input_dir + '*.shp'))


def parallel_shp2raster(shp_file, output_dir, burn_value=None, value_field=None, value_field_pos=0, xres=1000,
                        yres=1000, gridding=True, smoothing=4800, gdal_path='/usr/local/Cellar/gdal/2.4.2/bin/'):
    """
    Use this from #shp2rasters to parallelize raster creation
    :param shp_file: Input shapefile
    :param output_dir: Output directory
    :param burn_value: Set a fixed burn value instead of using value_field.
    :param value_field: Name of the value attribute. Set None to use value_field_pos
    :param value_field_pos: Value field position (zero indexing)
    :param xres: Pixel width in geographic units
    :param yres: Pixel height in geographic units
    :param gridding: Set false to use gdal_rasterize (If gridding is True, the Inverse Distance Square algorithm used
    with default parameters)
    :param smoothing: Level of smoothing (higher values imply higher smoothing effect)
    :param gdal_path: GDAL directory path, in Windows replace with OSGeo4W directory path, e.g. '/usr/bin/gdal/' on
    Linux or Mac and 'C:/OSGeo4W64/' on Windows, the '/' at the end is mandatory
    :return: None
    """

    outfile_path = output_dir + shp_file[shp_file.rfind(os.sep) + 1: shp_file.rfind('.') + 1] + 'tif'
    shp2raster(shp_file, outfile_path=outfile_path, value_field=value_field, value_field_pos=value_field_pos, xres=xres,
               yres=yres, burn_value=burn_value, gdal_path=gdal_path, gridding=gridding, smoothing=smoothing)


def extract_gdb_data(input_gdb_dir, attr_name, year_list, outdir, source_crs='epsg:4326', target_crs='epsg:4326',
                     shpfile=True, shp_file_prefix='GW'):
    """
    Extract yearly data from GDB and store them in separate files
    :param input_gdb_dir: Input GDB directory
    :param attr_name: Attribute name to extract data from
    :param year_list: List of years to extract
    :param outdir: Output directory
    :param source_crs: CRS of the source file
    :param target_crs: Target CRS
    :param shpfile: Set False to store output files in CSV format (default is SHP)
    :param shp_file_prefix: Prefix for output SHP file names
    :return: None
    """

    num_layers = len(fiona.listlayers(input_gdb_dir))
    gdb_data = gpd.read_file(input_gdb_dir, driver='FileGDB', layer=num_layers - 1)
    attr_list = [attr_name + '_' + str(year) for year in year_list]
    num_cores = multiprocessing.cpu_count()
    Parallel(n_jobs=num_cores)(delayed(parallel_gdb_extract)(gdb_data, index=index, attr=attr, year_list=year_list,
                                                             outdir=outdir, source_crs=source_crs,
                                                             target_crs=target_crs, shpfile=shpfile,
                                                             shp_file_prefix=shp_file_prefix)
                               for index, attr in enumerate(attr_list))


def parallel_gdb_extract(gdb_data, index, attr, year_list, outdir, source_crs='epsg:4326', target_crs='epsg:4326',
                         shpfile=True, shp_file_prefix='GW'):
    """
    Use this from #extract_gdb_data to parallely extract GDB data
    :param gdb_data: Geodatabase data as GeoDataFrame
    :param index: Year index
    :param attr: Attribute name to extract data from
    :param year_list: List of years to extract
    :param outdir: Output directory
    :param source_crs: CRS of the source file
    :param target_crs: Target CRS
    :param shpfile: Set False to store output files in CSV format (default is SHP)
    :param shp_file_prefix: Prefix for output SHP file names
    :return: None
    """

    outfile = outdir + shp_file_prefix + '_' + str(year_list[index])
    print('Writing...', attr)
    if shpfile:
        outfile += '.shp'
        gdf2shp(gdb_data[attr], geometry=gdb_data['geometry'], source_crs=source_crs, target_crs=target_crs,
                outfile_path=outfile)
    else:
        outfile += '.csv'
        df = gdb_data[[attr, 'geometry']]
        df.to_csv(outfile, mode='w', index=False)


def extract_polygons(input_shp_file, out_dir, label_attr='GMD_label'):
    """
    Extract and write individual polygons present in a shape file to output directory
    :param input_shp_file: Input shapefile
    :param out_dir: Output directory, the files are named based on the polygon labels
    :param label_attr: Label attribute present in the shapefile
    :return: None
    """

    out_dir = make_proper_dir_name(out_dir)
    input_shp_file = gpd.read_file(input_shp_file)
    for label in input_shp_file[label_attr]:
        outfile = out_dir + label + '.shp'
        feature = input_shp_file[input_shp_file[label_attr] == label]
        feature.to_file(outfile)
