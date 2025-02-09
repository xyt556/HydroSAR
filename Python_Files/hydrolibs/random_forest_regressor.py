# Author: Sayantan Majumdar
# Email: smxnv@mst.edu

import sklearn.utils as sk
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import pickle
import os
from glob import glob
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split, GridSearchCV
from collections import defaultdict
from sklearn.inspection import plot_partial_dependence
from sklearn.inspection import partial_dependence
from sklearn.inspection import permutation_importance
from mpl_toolkits.mplot3d import axes3d
from Python_Files.hydrolibs import rasterops as rops
from Python_Files.hydrolibs import model_analysis as ma


def create_dataframe(input_file_dir, input_gw_file, output_dir, label_attr, column_names=None, pattern='*.tif',
                     exclude_years=(), exclude_vars=(), make_year_col=True, ordering=False, load_gw_info=False,
                     remove_na=True):
    """
    Create dataframe from file list
    :param input_file_dir: Input directory where the file names begin with <Variable>_<Year>, e.g, ET_2015.tif
    :param input_gw_file: Input GMD (Kansas) or AMA/INA (Arizona) shape file
    :param output_dir: Output directory
    :param label_attr: Label attribute present in the GW shapefile. Set 'GMD_label' for Kansas and
    'NAME_ABBR' for Arizona
    :param column_names: Dataframe column names, these must be df headers
    :param pattern: File pattern to look for in the folder
    :param exclude_years: Exclude these years from the dataframe
    :param exclude_vars: Exclude these variables from the dataframe
    :param make_year_col: Make a dataframe column entry for year
    :param ordering: Set True to order dataframe column names
    :param load_gw_info: Set True to load previously created GWinfo raster containing the name of the GMD (Kansas) or
    AMA/INA (Arizona) regions
    :param remove_na: Set False to disable NA removal
    :return: GMD Numpy array
    :return: Pandas dataframe
    """

    raster_file_dict = defaultdict(lambda: [])
    for f in glob(input_file_dir + pattern):
        sep = f.rfind('_')
        variable, year = f[f.rfind(os.sep) + 1: sep], f[sep + 1: f.rfind('.')]
        if variable not in exclude_vars and int(year) not in exclude_years:
            raster_file_dict[int(year)].append(f)
    raster_dict = {}
    flag = False
    years = sorted(list(raster_file_dict.keys()))
    df = None
    raster_arr = None
    gw_arr = rops.get_gw_info_arr(raster_file_dict[years[0]][0], input_gw_file, output_dir=output_dir,
                                    label_attr=label_attr, load_gw_info=load_gw_info)
    gw_arr = gw_arr.ravel()
    for year in years:
        file_list = raster_file_dict[year]
        for raster_file in file_list:
            raster_arr = rops.read_raster_as_arr(raster_file, get_file=False)
            raster_arr = raster_arr.reshape(raster_arr.shape[0] * raster_arr.shape[1])
            variable = raster_file[raster_file.rfind(os.sep) + 1: raster_file.rfind('_')]
            raster_dict[variable] = raster_arr
        if make_year_col:
            raster_dict['YEAR'] = [year] * raster_arr.shape[0]
        if not flag:
            df = pd.DataFrame(data=raster_dict)
            flag = True
        else:
            df = df.append(pd.DataFrame(data=raster_dict))
    df['GW_NAME'] = gw_arr.tolist() * len(years)
    if remove_na:
        df = df.dropna(axis=0)
    df = reindex_df(df, column_names=column_names, ordering=ordering)
    out_df = output_dir + 'raster_df.csv'
    df.to_csv(out_df, index=False)
    return df


def reindex_df(df, column_names, ordering=False):
    """
    Reindex dataframe columns
    :param df: Input dataframe
    :param column_names: Dataframe column names, these must be df headers
    :param ordering: Set True to apply ordering
    :return: Reindexed dataframe
    """
    if not column_names:
        column_names = df.columns
        ordering = True
    if ordering:
        column_names = sorted(column_names)
    return df.reindex(column_names, axis=1)


def get_rf_model(rf_file):
    """
    Get existing RF model object
    :param rf_file: File path to RF model
    :return: RandomForestRegressor
    """

    return pickle.load(open(rf_file, mode='rb'))


def split_data_train_test_ratio(input_df, pred_attr='GW', shuffle=True, random_state=0, test_size=0.2, outdir=None,
                                test_year=None, test_gw=None, use_gw=False):
    """
    Split data based on train-test percentage
    :param input_df: Input dataframe
    :param pred_attr: Prediction attribute name
    :param shuffle: Default True for shuffling
    :param random_state: Random state used during train test split
    :param test_size: Test data size percentage (0<=test_size<=1)
    :param outdir: Set path to store intermediate files
    :param test_year: Build test data from only this year
    :param test_gw: Build test data from only this GMD or AMA/INA region, use_gw must be set to True
    :param use_gw: Set True to build test data from only test_gmd
    :return: X_train, X_test, y_train, y_test
    """

    years = set(input_df['YEAR'])
    gws = set(input_df['GW_NAME'])
    x_train_df = pd.DataFrame()
    x_test_df = pd.DataFrame()
    y_train_df = pd.DataFrame()
    y_test_df = pd.DataFrame()
    flag = False
    if (test_year in years) or (use_gw and test_gw in gws):
        flag = True
    selection_var = years
    selection_label = 'YEAR'
    test_var = test_year
    if use_gw:
        selection_var = gws
        selection_label = 'GW_NAME'
        test_var = test_gw
    for svar in selection_var:
        selected_data = input_df.loc[input_df[selection_label] == svar]
        y = selected_data[pred_attr]
        x_train, x_test, y_train, y_test = train_test_split(selected_data, y, shuffle=shuffle,
                                                            random_state=random_state, test_size=test_size)
        x_train_df = x_train_df.append(x_train)
        if (flag and test_var == svar) or not flag:
            x_test_df = x_test_df.append(x_test)
            y_test_df = pd.concat([y_test_df, y_test])
        y_train_df = pd.concat([y_train_df, y_train])

    if outdir:
        x_train_df.to_csv(outdir + 'X_Train.csv', index=False)
        x_test_df.to_csv(outdir + 'X_Test.csv', index=False)
        y_train_df.to_csv(outdir + 'Y_Train.csv', index=False)
        y_test_df.to_csv(outdir + 'Y_Test.csv', index=False)

    return x_train_df, x_test_df, y_train_df[0].ravel(), y_test_df[0].ravel()


def split_data_attribute(input_df, pred_attr='GW', outdir=None, test_years=(2016, ), test_gws=('DIN',),
                         use_gws=False, shuffle=True, random_state=0, spatio_temporal=False):
    """
    Split data based on a particular attribute like year or GMD
    :param input_df: Input dataframe
    :param pred_attr: Prediction attribute name
    :param outdir: Set path to store intermediate files
    :param test_years: Build test data from only these years
    :param test_gws: Build test data from only these GMDs or AMA/INA regions, use_gws must be set to True
    :param use_gws: Set True to build test data from only test_gws
    :param shuffle: Set False to stop data shuffling
    :param random_state: Seed for PRNG
    :param spatio_temporal: Set True to build test from both test_years and test_gws
    :return: X_train, X_test, y_train, y_test
    """

    years = set(input_df['YEAR'])
    gws = set(input_df['GW_NAME'])
    x_train_df = pd.DataFrame()
    x_test_df = pd.DataFrame()
    selection_var = years
    selection_label = 'YEAR'
    test_vars = test_years
    if use_gws:
        selection_var = gws
        selection_label = 'GW_NAME'
        test_vars = test_gws
    for svar in selection_var:
        selected_data = input_df.loc[input_df[selection_label] == svar]
        x_t = selected_data
        if svar not in test_vars:
            x_train_df = x_train_df.append(x_t)
        else:
            x_test_df = x_test_df.append(x_t)
    if spatio_temporal and use_gws:
        for year in test_years:
            x_test_new = x_train_df.loc[x_train_df['YEAR'] == year]
            x_test_df = x_test_df.append(x_test_new)
            x_train_df = x_train_df.loc[x_train_df['YEAR'] != year]
    y_train_df = x_train_df[pred_attr]
    y_test_df = x_test_df[pred_attr]
    if shuffle:
        x_train_df = sk.shuffle(x_train_df, random_state=random_state)
        y_train_df = sk.shuffle(y_train_df, random_state=random_state)
        x_test_df = sk.shuffle(x_test_df, random_state=random_state)
        y_test_df = sk.shuffle(y_test_df, random_state=random_state)
    if outdir:
        x_train_df.to_csv(outdir + 'X_Train.csv', index=False)
        x_test_df.to_csv(outdir + 'X_Test.csv', index=False)
        y_train_df.to_csv(outdir + 'Y_Train.csv', index=False)
        y_test_df.to_csv(outdir + 'Y_Test.csv', index=False)

    return x_train_df, x_test_df, y_train_df.to_numpy().ravel(), y_test_df.to_numpy().ravel()


def create_pdplots(x_train, rf_model, outdir, plot_3d=False, descriptive_labels=False):
    """
    Create partial dependence plots
    :param x_train: Training set
    :param rf_model: Random Forest model
    :param outdir: Output directory for storing partial dependence data
    :param plot_3d: Set True for creating pairwise 3D plots
    :param descriptive_labels: Set True to get descriptive labels
    :return: None
    """

    print('Plotting...')
    feature_names = x_train.columns.values.tolist()
    plot_labels = {'AGRI': 'AGRI', 'URBAN': 'URBAN', 'SW': 'SW', 'SSEBop': 'ET (mm)', 'P': 'P (mm)', 'Crop': 'CC',
                   'WS_PA': 'WS_PA', 'WS_PA_EA': 'WS_PA_EA'}
    if descriptive_labels:
        plot_labels = {'AGRI': 'Agriculture density', 'URBAN': 'Urban density', 'SW': 'Surface water density',
                       'ET': 'Evapotranspiration (mm)', 'P': 'Precipitation (mm)'}
    feature_indices = range(len(feature_names))
    feature_dict = {}
    if plot_3d:
        x_train = x_train[:500]
        for fi in feature_indices:
            for fj in feature_indices:
                feature_check = (fi != fj) and ((fi, fj) not in feature_dict.keys()) and ((fj, fi) not in
                                                                                          feature_dict.keys())
                if feature_check:
                    print(feature_names[fi], feature_names[fj])
                    feature_dict[(fi, fj)] = True
                    feature_dict[(fj, fi)] = True
                    f_pefix = outdir + 'PDP_' + feature_names[fi] + '_' + feature_names[fj]
                    saved_files = glob(outdir + '*' + feature_names[fi] + '_' + feature_names[fj] + '*')
                    if not saved_files:
                        pdp, axes = partial_dependence(rf_model, x_train, features=(fi, fj))
                        x, y = np.meshgrid(axes[0], axes[1])
                        z = pdp[0].T
                        np.save(f_pefix + '_X', x)
                        np.save(f_pefix + '_Y', y)
                        np.save(f_pefix + '_Z', z)
                    else:
                        x = np.load(f_pefix + '_X.npy')
                        y = np.load(f_pefix + '_Y.npy')
                        z = np.load(f_pefix + '_Z.npy')
                    fig = plt.figure()
                    ax = axes3d.Axes3D(fig)
                    surf = ax.plot_surface(x, y, z, cmap='viridis', edgecolor='k')
                    ax.set_xlabel(plot_labels[feature_names[fi]])
                    ax.set_ylabel(plot_labels[feature_names[fj]])
                    ax.set_zlabel('GW Pumping (mm)')
                    plt.colorbar(surf, shrink=0.3, aspect=5)
                    plt.show()
    else:
        fnames = []
        for name in feature_names:
            fnames.append(plot_labels[name])
        plot_partial_dependence(rf_model, features=feature_indices, X=x_train, feature_names=fnames, n_jobs=-1)
        plt.tight_layout(pad=0.4, w_pad=0.5, h_pad=1.0)
        plt.show()


def rf_regressor(input_df, out_dir, n_estimators=500, random_state=0, bootstrap=True, max_features=None, test_size=0.2,
                 pred_attr='GW', shuffle=True, plot_graphs=False, plot_3d=False, plot_dir=None, drop_attrs=(),
                 test_case='', test_year=None, test_gw=None, use_gw=False, split_attribute=True, load_model=True,
                 calc_perm_imp=False, spatio_temporal=False):
    """
    Perform random forest regression
    :param input_df: Input pandas dataframe
    :param out_dir: Output file directory for storing intermediate results
    :param n_estimators: RF hyperparameter
    :param random_state: RF hyperparameter
    :param bootstrap: RF hyperparameter
    :param max_features: RF hyperparameter
    :param test_size: Required only if split_yearly=False
    :param pred_attr: Prediction attribute name in the dataframe
    :param shuffle: Set False to stop data shuffling
    :param plot_graphs: Plot Actual vs Prediction graph
    :param plot_3d: Plot pairwise 3D partial dependence plots
    :param plot_dir: Directory for storing PDP data
    :param drop_attrs: Drop these specified attributes
    :param test_case: Used for writing the test case number to the CSV
    :param test_year: Build test data from only this year. Use tuple of years to split train and test data using
    #split_data_attribute
    :param test_gw: Build test data from only this GMD (Kansas) or AMA/INA (Arizona) region, use_gw must be set to True.
    Use tuple of years to split train and test data using #split_data_attribute
    :param use_gw: Set True to build test data from only test_gw
    :param split_attribute: Split train test data based on a particular attribute like year or GMD
    :param load_model: Load an earlier pre-trained RF model
    :param calc_perm_imp: Set True to get permutation importances on train and test data
    :param spatio_temporal: Set True to build test from both test_years and test_gws
    :return: Random forest model
    """

    saved_model = glob(out_dir + '*rf_model*')
    if load_model and saved_model:
        regressor = get_rf_model(saved_model[0])
        x_train = pd.read_csv(out_dir + 'X_Train.csv')
        y_train = pd.read_csv(out_dir + 'Y_Train.csv')
        x_test = pd.read_csv(out_dir + 'X_Test.csv')
        y_test = pd.read_csv(out_dir + 'Y_Test.csv')
        drop_columns = [pred_attr] + list(drop_attrs)
        x_train = x_train.drop(columns=drop_columns)
        x_test = x_test.drop(columns=drop_columns)
    else:
        if not split_attribute:
            x_train, x_test, y_train, y_test = split_data_train_test_ratio(input_df, pred_attr=pred_attr,
                                                                           test_size=test_size,
                                                                           random_state=random_state, shuffle=shuffle,
                                                                           outdir=out_dir, test_year=test_year,
                                                                           test_gw=test_gw, use_gw=use_gw)
        else:
            x_train, x_test, y_train, y_test = split_data_attribute(input_df, pred_attr=pred_attr, outdir=out_dir,
                                                                    test_years=test_year, shuffle=shuffle,
                                                                    random_state=random_state, test_gws=test_gw,
                                                                    use_gws=use_gw, spatio_temporal=spatio_temporal)
        drop_columns = [pred_attr] + list(drop_attrs)
        x_train = x_train.drop(columns=drop_columns)
        x_test = x_test.drop(columns=drop_columns)
        # param_grid = [{'n_estimators': [500],
        #                'max_features': [7],
        #                'max_depth': [10],
        #                'random_state': [random_state]
        #                }]
        #
        # print('Running RF GridSearchCV...')
        # regressor = GridSearchCV(RandomForestRegressor(n_jobs=-2, oob_score=True, bootstrap=bootstrap),
        #                                param_grid,
        #                                n_jobs=-2,
        #                                cv=2,
        #                                scoring=['neg_root_mean_squared_error'],
        #                                refit='neg_root_mean_squared_error')
        regressor = RandomForestRegressor(n_jobs=-2, oob_score=True, bootstrap=bootstrap, n_estimators=n_estimators,
                                          max_features=max_features, random_state=random_state, max_depth=18,
                                          max_samples=None, min_samples_leaf=1e-5, min_samples_split=2,
                                          max_leaf_nodes=None, min_impurity_decrease=0., min_weight_fraction_leaf=0.,
                                          ccp_alpha=0.)
        regressor.fit(x_train, y_train)
        pickle.dump(regressor, open(out_dir + 'rf_model', mode='wb'))

    # print(regressor.best_params_)
    print('Predictor... ')
    y_pred_train = regressor.predict(x_train)
    y_pred_test = regressor.predict(x_test)
    feature_imp = " ".join(str(np.round(i, 2)) for i in regressor.feature_importances_)
    permutation_imp_train, permutation_imp_test = None, None
    if calc_perm_imp:
        permutation_imp_train = permutation_importance(regressor, x_train, y_train, n_repeats=10, n_jobs=-1,
                                                       random_state=random_state)
        permutation_imp_train = " ".join(str(np.round(i, 2)) for i in permutation_imp_train.importances_mean)
        permutation_imp_test = permutation_importance(regressor, x_test, y_test, n_repeats=10, n_jobs=-1,
                                                      random_state=random_state)
        permutation_imp_test = " ".join(str(np.round(i, 2)) for i in permutation_imp_test.importances_mean)
    train_r2_score, train_mae, train_rmse, train_nmae, train_nrmse = ma.get_error_stats(y_train, y_pred_train)
    test_r2_score, test_mae, test_rmse, test_nmae, test_nrmse = ma.get_error_stats(y_test, y_pred_test)
    oob_score = np.round(regressor.oob_score_, 2)
    df = {'Test': [test_case], 'F_IMP': [feature_imp], 'Train_Score': [train_r2_score], 'Test_Score': [test_r2_score],
          'Train_MAE': [train_mae], 'Test_MAE': [test_mae], 'Train_RMSE': [train_rmse],
          'Test_RMSE': [test_rmse], 'Train_NMAE': [train_nmae], 'Test_NMAE': [test_nmae], 'Train_NRMSE': [train_nrmse],
          'Test_NRMSE': [test_nrmse], 'OOB_Score': [oob_score]}
    if calc_perm_imp:
        df['P_IMP_TRAIN'], df['P_IMP_TEST'] = [permutation_imp_train], [permutation_imp_test]
    print(x_train.columns)
    print('Model statistics:', df)
    df = pd.DataFrame(data=df)
    with open(out_dir + 'RF_Results.csv', 'a') as f:
        df.to_csv(f, mode='a', index=False, header=f.tell() == 0)
    if plot_graphs:
        create_pdplots(x_train=x_train, rf_model=regressor, outdir=plot_dir, plot_3d=plot_3d)
    return regressor


def create_pred_raster(rf_model, out_raster, actual_raster_dir, column_names=None, exclude_vars=(), pred_year=2015,
                       pred_attr='GW', drop_attrs=(), only_pred=False, calculate_errors=True, ordering=False):
    """
    Create prediction raster
    :param rf_model: Pre-built Random Forest Model
    :param out_raster: Output raster
    :param actual_raster_dir: Ground truth raster files required for prediction
    :param column_names: Dataframe column names, these must be df headers
    :param exclude_vars: Exclude these variables from the model prediction and analysis
    :param pred_year: Prediction year
    :param pred_attr: Prediction attribute name in the dataframe
    :param drop_attrs: Drop these specified attributes (Must be exactly the same as used in rf_regressor module)
    :param only_pred: Set True to disable raster creation and for showing only the error metrics,
    automatically set to False if calculate_errors is False
    :param calculate_errors: Calculate error metrics if actual observations are present
    :param ordering: Set True to order dataframe column names
    :return: MAE, RMSE, and R^2 statistics (rounded to 2 decimal places)
    """

    raster_files = glob(actual_raster_dir + '*_' + str(pred_year) + '*.tif')
    raster_arr_dict = {}
    nan_pos_dict = {}
    actual_file = None
    raster_shape = None
    for raster_file in raster_files:
        sep = raster_file.rfind('_')
        variable, year = raster_file[raster_file.rfind(os.sep) + 1: sep], raster_file[sep + 1: raster_file.rfind('.')]
        if variable not in exclude_vars:
            raster_arr, actual_file = rops.read_raster_as_arr(raster_file)
            raster_shape = raster_arr.shape
            raster_arr = raster_arr.reshape(raster_shape[0] * raster_shape[1])
            nan_pos_dict[variable] = np.isnan(raster_arr)
            if not only_pred:
                raster_arr[nan_pos_dict[variable]] = 0
            raster_arr_dict[variable] = raster_arr
            raster_arr_dict['YEAR'] = [year] * raster_arr.shape[0]

    input_df = pd.DataFrame(data=raster_arr_dict)
    input_df = input_df.dropna(axis=0)
    input_df = reindex_df(input_df, column_names=column_names, ordering=ordering)
    drop_columns = [pred_attr] + list(drop_attrs)
    if not calculate_errors:
        drop_cols = drop_columns
        if not column_names:
            drop_cols.remove(pred_attr)
        input_df = input_df.drop(columns=drop_cols)
        pred_arr = rf_model.predict(input_df)
        if not only_pred:
            for nan_pos in nan_pos_dict.values():
                pred_arr[nan_pos] = actual_file.nodata
        mae, rmse, r2_score, nrmse, nmae = (np.nan, ) * 5
    else:
        if only_pred:
            actual_arr = input_df[pred_attr]
        else:
            actual_arr = raster_arr_dict[pred_attr]
        input_df = input_df.drop(columns=drop_columns)
        pred_arr = rf_model.predict(input_df)
        if not only_pred:
            for nan_pos in nan_pos_dict.values():
                actual_arr[nan_pos] = actual_file.nodata
                pred_arr[nan_pos] = actual_file.nodata
            actual_values = actual_arr[actual_arr != actual_file.nodata]
            pred_values = pred_arr[pred_arr != actual_file.nodata]
        else:
            actual_values = actual_arr
            pred_values = pred_arr
        r2_score, mae, rmse, nmae, nrmse = ma.get_error_stats(actual_values, pred_values)
    if not only_pred:
        pred_arr = pred_arr.reshape(raster_shape)
        rops.write_raster(pred_arr, actual_file, transform=actual_file.transform, outfile_path=out_raster)
    return mae, rmse, r2_score, nrmse, nmae


def predict_rasters(rf_model, actual_raster_dir, out_dir, pred_years, column_names=None, drop_attrs=(), pred_attr='GW',
                    only_pred=False, exclude_vars=(), exclude_years=(2019,), ordering=False):
    """
    Create prediction rasters from input data
    :param rf_model: Pre-trained Random Forest Model
    :param actual_raster_dir: Directory containing input rasters
    :param out_dir: Output directory for predicted rasters
    :param pred_years: Tuple containing prediction years
    :param column_names: Dataframe column names, these must be df headers
    :param drop_attrs: Drop these specified attributes (Must be exactly the same as used in rf_regressor module)
    :param pred_attr: Prediction Attribute
    :param only_pred: Set true to disable raster creation and for showing only the error metrics
    :param exclude_vars: Exclude these variables from the model prediction
    :param exclude_years: Exclude these years from error analysis, only the respective predicted rasters are generated
    :param ordering: Set True to order dataframe column names
    :return: None
    """

    for pred_year in pred_years:
        out_pred_raster = out_dir + 'pred_' + str(pred_year) + '.tif'
        calculate_errors = True
        if pred_year in exclude_years:
            calculate_errors = False
        mae, rmse, r_squared, normalized_rmse, normalized_mae = create_pred_raster(rf_model, out_raster=out_pred_raster,
                                                                                   actual_raster_dir=actual_raster_dir,
                                                                                   exclude_vars=exclude_vars,
                                                                                   pred_year=pred_year,
                                                                                   drop_attrs=drop_attrs,
                                                                                   pred_attr=pred_attr,
                                                                                   only_pred=only_pred,
                                                                                   calculate_errors=calculate_errors,
                                                                                   column_names=column_names,
                                                                                   ordering=ordering)
        print('YEAR', pred_year, ': MAE =', mae, 'RMSE =', rmse, 'R^2 =', r_squared,
              'Normalized RMSE =', normalized_rmse, 'Normalized MAE =', normalized_mae)
