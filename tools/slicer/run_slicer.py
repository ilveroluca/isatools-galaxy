"""Functions for slicing ISA-Tabs, based on the mtbls.py module.
"""
#!/usr/bin/env python3

from __future__ import absolute_import
import argparse
import glob
import logging
import os
import pandas as pd
import re
import sys


from isatools import isatab
from isatools.model import OntologyAnnotation


log = logging.getLogger('isatools')

# REGEXES
_RX_FACTOR_VALUE = re.compile('Factor Value\[(.*?)\]')

def make_parser():
    parser = argparse.ArgumentParser(
        description="ISA slicer - a wrapper for isatools.io.mtbls")

    parser.add_argument('--log-level', choices=[
        'DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL'],
                        default='INFO', help="Set the desired logging level")

    subparsers = parser.add_subparsers(
        title='Actions',
        dest='command') # specified subcommand will be available in attribute 'command'
    subparsers.required = True

    subparser = subparsers.add_parser(
        'get-factors', aliases=['gf'],
        help="Get factor names from a study in json format")
    subparser.set_defaults(func=get_factors_command)
    subparser.add_argument('study_id')
    subparser.add_argument(
        'output', nargs='?', type=argparse.FileType('w'), default=sys.stdout,
        help="Output file")

    subparser = subparsers.add_parser(
        'get-factor-values', aliases=['gfv'],
        help="Get factor values from a study in json format")
    subparser.set_defaults(func=get_factor_values_command)
    subparser.add_argument('study_id')
    subparser.add_argument(
        'factor', help="The desired factor. Use `get-factors` to get the list "
                       "of available factors")
    subparser.add_argument(
        'output',nargs='?', type=argparse.FileType('w'), default=sys.stdout,
        help="Output file")

    subparser = subparsers.add_parser('get-data', aliases=['gd'],
                                      help="Get data files in json format")
    subparser.set_defaults(func=get_data_files_command)
    subparser.add_argument('study_id')
    subparser.add_argument('output',nargs='?', type=argparse.FileType('w'), default=sys.stdout,
                           help="Output file")

    subparser.add_argument(
        '--json-query',
        help="Factor query in JSON (e.g., '{\"Gender\":\"Male\"}'")

    subparser = subparsers.add_parser(
        'get-summary', aliases=['gsum'],
        help="Get the variables summary from a study, in json format")
    subparser.set_defaults(func=get_summary_command)
    subparser.add_argument('study_id')
    subparser.add_argument(
        'output', nargs='?', type=argparse.FileType('w'), default=sys.stdout,
        help="Output file")

    return parser


def get_data_files(input_path, factor_selection=None):
    result = slice_data_files(input_path, factor_selection=factor_selection)
    return result


def slice_data_files(dir, factor_selection=None):
    """
    This function gets a list of samples and related data file URLs for a given
    MetaboLights study, optionally filtered by factor value (currently by
    matching on exactly 1 factor value)

    :param input_path: Input path to ISA-tab
    :param factor_selection: A list of selected factor values to filter on
    samples
    :return: A list of dicts {sample_name, list of data_files} containing
    sample names with associated data filenames


    TODO:  Need to work on more complex filters e.g.:
        {"gender": ["male", "female"]} selects samples matching "male" or
        "female" factor value
        {"age": {"equals": 60}} selects samples matching age 60
        {"age": {"less_than": 60}} selects samples matching age less than 60
        {"age": {"more_than": 60}} selects samples matching age more than 60

        To select samples matching "male" and age less than 60:
        {
            "gender": "male",
            "age": {
                "less_than": 60
            }
        }
    """
    results = []
    # first collect matching samples
    for table_file in glob.iglob(os.path.join(dir, '[a|s]_*')):
        log.info('Loading {table_file}'.format(table_file=table_file))

        with open(os.path.join(dir, table_file)) as fp:
            df = isatab.load_table(fp)

            if factor_selection is None:
                matches = df['Sample Name'].items()

                for indx, match in matches:
                    sample_name = match
                    if len([r for r in results if r['sample'] ==
                            sample_name]) == 1:
                        continue
                    else:
                        results.append(
                            {
                                'sample': sample_name,
                                'data_files': []
                            }
                        )

            else:
                for factor_name, factor_value in factor_selection.items():
                    if 'Factor Value[{}]'.format(factor_name) in list(
                            df.columns.values):
                        matches = df.loc[df['Factor Value[{factor}]'.format(
                            factor=factor_name)] == factor_value][
                            'Sample Name'].items()

                        for indx, match in matches:
                            sample_name = match
                            if len([r for r in results if r['sample'] ==
                                    sample_name]) == 1:
                                continue
                            else:
                                results.append(
                                    {
                                        'sample': sample_name,
                                        'data_files': [],
                                        'query_used': factor_selection
                                    }
                                )

    # now collect the data files relating to the samples
    for result in results:
        sample_name = result['sample']

        for table_file in glob.iglob(os.path.join(dir, 'a_*')):
            with open(table_file) as fp:
                df = isatab.load_table(fp)

                data_files = []

                table_headers = list(df.columns.values)
                sample_rows = df.loc[df['Sample Name'] == sample_name]

                if 'Raw Spectral Data File' in table_headers:
                    data_files = sample_rows['Raw Spectral Data File']

                elif 'Free Induction Decay Data File' in table_headers:
                    data_files = sample_rows['Free Induction Decay Data File']

                result['data_files'] = [i for i in list(data_files) if
                                        str(i) != 'nan']
    return results


def get_factor_names(input_path):
    """
    This function gets the factor names used in a MetaboLights study

    :param input_path: Input path to ISA-tab
    :return: A set of factor names used in the study

    Example usage:
        factor_names = get_factor_names('/path/to/my/study/')
    """

    factors = set()

    for table_file in glob.iglob(os.path.join(input_path, '[a|s]_*')):
        with open(os.path.join(input_path, table_file)) as fp:
            df = isatab.load_table(fp)

            factors_headers = [header for header in list(df.columns.values)
                               if _RX_FACTOR_VALUE.match(header)]

            for header in factors_headers:
                factors.add(header[13:-1])
    return factors


def get_factor_values(input_path, factor_name):
    """
    This function gets the factor values of a factor in a MetaboLights study

    :param input_path: Input path to ISA-tab
    :param factor_name: The factor name for which values are being queried
    :return: A set of factor values associated with the factor and study

    Example usage:
        factor_values = get_factor_values('/path/to/my/study/', 'genotype')
    """

    fvs = set()

    for table_file in glob.iglob(os.path.join(input_path, '[a|s]_*')):
        with open(os.path.join(input_path, table_file)) as fp:
            df = isatab.load_table(fp)

            if 'Factor Value[{factor}]'.format(factor=factor_name) in \
                    list(df.columns.values):
                for _, match in df[
                    'Factor Value[{factor}]'.format(
                        factor=factor_name)].iteritems():
                    try:
                        match = match.item()
                    except AttributeError:
                        pass

                    if isinstance(match, (str, int, float)):
                        if str(match) != 'nan':
                            fvs.add(match)
    return fvs


def get_factors_summary(input_path):
    """
    This function generates a factors summary for a MetaboLights study

    :param input_path: Input path to ISA-tab
    :return: A list of dicts summarising the set of factor names and values
    associated with each sample

    Note: it only returns a summary of factors with variable values.

    Example usage:
        factor_summary = get_factors_summary('/path/to/my/study/')
        [
            {
                "name": "ADG19007u_357",
                "Metabolic syndrome": "Control Group",
                "Gender": "Female"
            },
            {
                "name": "ADG10003u_162",
                "Metabolic syndrome": "diabetes mellitus",
                "Gender": "Female"
            },
        ]


    """
    ISA = isatab.load(input_path)

    all_samples = []
    for study in ISA.studies:
        all_samples.extend(study.samples)

    samples_and_fvs = []

    for sample in all_samples:
        sample_and_fvs = {
                'sources': ';'.join([x.name for x in sample.derives_from]),
                'sample': sample.name,
            }

        for fv in sample.factor_values:
            if isinstance(fv.value, (str, int, float)):
                fv_value = fv.value
                sample_and_fvs[fv.factor_name.name] = fv_value
            elif isinstance(fv.value, OntologyAnnotation):
                fv_value = fv.value.term
                sample_and_fvs[fv.factor_name.name] = fv_value

        samples_and_fvs.append(sample_and_fvs)

    df = pd.DataFrame(samples_and_fvs)
    nunique = df.apply(pd.Series.nunique)
    cols_to_drop = nunique[nunique == 1].index

    df = df.drop(cols_to_drop, axis=1)
    return df.to_dict(orient='records')


def get_study_groups(input_path):
    factors_summary = get_factors_summary(input_path=input_path)
    study_groups = {}

    for factors_item in factors_summary:
        fvs = tuple(factors_item[k] for k in factors_item.keys() if k != 'name')

        if fvs in study_groups.keys():
            study_groups[fvs].append(factors_item['name'])
        else:
            study_groups[fvs] = [factors_item['name']]
    return study_groups


def get_study_groups_samples_sizes(input_path):
    study_groups = get_study_groups(input_path=input_path)
    return list(map(lambda x: (x[0], len(x[1])), study_groups.items()))


def get_sources_for_sample(input_path, sample_name):
    ISA = isatab.load(input_path)
    hits = []

    for study in ISA.studies:
        for sample in study.samples:
            if sample.name == sample_name:
                print('found a hit: {sample_name}'.format(
                    sample_name=sample.name))

                for source in sample.derives_from:
                    hits.append(source.name)
    return hits


def get_data_for_sample(input_path, sample_name):
    ISA = isatab.load(input_path)
    hits = []
    for study in ISA.studies:
        for assay in study.assays:
            for data in assay.data_files:
                if sample_name in [x.name for x in data.generated_from]:
                    log.info('found a hit: {filename}'.format(
                        filename=data.filename))
                    hits.append(data)
    return hits


def get_study_groups_data_sizes(input_path):
    study_groups = get_study_groups(input_path=input_path)
    return list(map(lambda x: (x[0], len(x[1])), study_groups.items()))


def get_characteristics_summary(input_path):
    """
        This function generates a characteristics summary for a MetaboLights
        study

        :param input_path: Input path to ISA-tab
        :return: A list of dicts summarising the set of characteristic names
        and values associated with each sample

        Note: it only returns a summary of characteristics with variable values.

        Example usage:
            characteristics_summary = get_characteristics_summary('/path/to/my/study/')
            [
                {
                    "name": "6089if_9",
                    "Variant": "Synechocystis sp. PCC 6803.sll0171.ko"
                },
                {
                    "name": "6089if_43",
                    "Variant": "Synechocystis sp. PCC 6803.WT.none"
                },
            ]


        """
    ISA = isatab.load(input_path)

    all_samples = []
    for study in ISA.studies:
        all_samples.extend(study.samples)

    samples_and_characs = []
    for sample in all_samples:
        sample_and_characs = {
                'name': sample.name
            }

        for source in sample.derives_from:
            for c in source.characteristics:
                if isinstance(c.value, (str, int, float)):
                    c_value = c.value
                    sample_and_characs[c.category.term] = c_value
                elif isinstance(c.value, OntologyAnnotation):
                    c_value = c.value.term
                    sample_and_characs[c.category.term] = c_value

        samples_and_characs.append(sample_and_characs)

    df = pd.DataFrame(samples_and_characs)
    nunique = df.apply(pd.Series.nunique)
    cols_to_drop = nunique[nunique == 1].index

    df = df.drop(cols_to_drop, axis=1)
    return df.to_dict(orient='records')


def get_study_variable_summary(input_path):
    ISA = isatab.load(input_path)

    all_samples = []
    for study in ISA.studies:
        all_samples.extend(study.samples)

    samples_and_variables = []
    for sample in all_samples:
        sample_and_vars = {
            'sample_name': sample.name
        }

        for fv in sample.factor_values:
            if isinstance(fv.value, (str, int, float)):
                fv_value = fv.value
                sample_and_vars[fv.factor_name.name] = fv_value
            elif isinstance(fv.value, OntologyAnnotation):
                fv_value = fv.value.term
                sample_and_vars[fv.factor_name.name] = fv_value

        for source in sample.derives_from:
            sample_and_vars['source_name'] = source.name
            for c in source.characteristics:
                if isinstance(c.value, (str, int, float)):
                    c_value = c.value
                    sample_and_vars[c.category.term] = c_value
                elif isinstance(c.value, OntologyAnnotation):
                    c_value = c.value.term
                    sample_and_vars[c.category.term] = c_value

        samples_and_variables.append(sample_and_vars)

    df = pd.DataFrame(samples_and_variables)
    nunique = df.apply(pd.Series.nunique)
    cols_to_drop = nunique[nunique == 1].index

    df = df.drop(cols_to_drop, axis=1)
    return df.to_dict(orient='records')


def get_study_group_factors(input_path):
    factors_list = []

    for table_file in glob.iglob(os.path.join(input_path, '[a|s]_*')):
        with open(os.path.join(input_path, table_file)) as fp:
            df = isatab.load_table(fp)

            factor_columns = [x for x in df.columns if x.startswith(
                'Factor Value')]
            if len(factor_columns) > 0:
                factors_list = df[factor_columns].drop_duplicates()\
                    .to_dict(orient='records')
    return factors_list


def get_filtered_df_on_factors_list(input_path):
    factors_list = get_study_group_factors(input_path=input_path)
    queries = []

    for item in factors_list:
        query_str = []

        for k, v in item.items():
            k = k.replace(' ', '_').replace('[', '_').replace(']', '_')
            if isinstance(v, str):
                v = v.replace(' ', '_').replace('[', '_').replace(']', '_')
                query_str.append("{k} == '{v}' and ".format(k=k, v=v))

        query_str = ''.join(query_str)[:-4]
        queries.append(query_str)

    for table_file in glob.iglob(os.path.join(input_path, '[a|s]_*')):
        with open(os.path.join(input_path, table_file)) as fp:
            df = isatab.load_table(fp)

            cols = df.columns
            cols = cols.map(
                lambda x: x.replace(' ', '_') if isinstance(x, str) else x)
            df.columns = cols

            cols = df.columns
            cols = cols.map(
                lambda x: x.replace('[', '_') if isinstance(x, str) else x)
            df.columns = cols

            cols = df.columns
            cols = cols.map(
                lambda x: x.replace(']', '_') if isinstance(x, str) else x)
            df.columns = cols

        for query in queries:
            df2 = df.query(query)  # query uses pandas.eval, which evaluates
                                   # queries like pure Python notation
            if 'Sample_Name' in df.columns:
                print('Group: {query} / Sample_Name: {sample_name}'.format(
                    query=query, sample_name=list(df2['Sample_Name'])))

            if 'Source_Name' in df.columns:
                print('Group: {} / Sources_Name: {}'.format(
                    query, list(df2['Source_Name'])))

            if 'Raw_Spectral_Data_File' in df.columns:
                print('Group: {query} / Raw_Spectral_Data_File: {filename}'
                    .format( query=query[13:-2],
                             filename=list(df2['Raw_Spectral_Data_File'])))
    return queries

def _configure_logger(options):
    logging_level = getattr(logging, options.log_level, logging.INFO)
    logging.basicConfig(level=logging_level)

    global logger
    logger = logging.getLogger()
    logger.setLevel(logging_level) # there's a bug somewhere.  The level set through basicConfig isn't taking effect

def _parse_args(args):
    parser = make_parser()
    options = parser.parse_args(args)

    # All subcommands have `study_id`
    # Can we check the format of the study ID here, and raise an informative error
    # if it's invalid?
    if not options.study_id:
        parser.error("study_id argument not provided")

    return options

def main(args):
    options = _parse_args(args)
    _configure_logger(options)

    if not options.study_id.startswith('MTBLS'):
        logger.warning(
            "The study id %s doesn't look like a valid Metabolights id",
            options.study_id)

    # run subcommand
    options.func(options)


def get_factors_command(options):
    import json

    logger.info("Getting factors for study %s. Writing to %s.",
                options.study_id, options.output.name)
    factor_names = get_factor_names(options.study_id)
    print('FNs: ', list(factor_names))
    if factor_names is not None:
        json.dump(list(factor_names), options.output, indent=4)
        logger.debug("Factor names written")
    else:
        raise RuntimeError("Error downloading factors.")

def get_factor_values_command(options):
    import json
    logger.info("Getting values for factor {factor} in study {study_id}. Writing to {output_file}."
        .format(factor=options.factor, study_id=options.study_id, output_file=options.output.name))

    fvs = get_factor_values(options.study_id, options.factor)
    print('FVs: ', list(fvs))
    if fvs is not None:
        json.dump(list(fvs), options.output, indent=4)
        logger.debug("Factor values written to {}".format(options.output))
    else:
        raise RuntimeError("Error getting factor values")

def get_data_files_command(options):
    import json
    logger.info("Getting data files for study %s. Writing to %s.",
                options.study_id, options.output.name)
    if options.json_query:
        logger.debug("This is the specified query:\n%s", options.json_query)
    else:
        logger.debug("No query was specified")

    if options.json_query is not None:
        json_struct = json.loads(options.json_query)
        data_files = get_data_files(options.study_id, json_struct)
    else:
        data_files = get_data_files(options.study_id)

    logger.debug("Result data files list: %s", data_files)
    if data_files is None:
        raise RuntimeError("Error getting data files with isatools")

    logger.debug("dumping data files to %s", options.output.name)
    json.dump(list(data_files), options.output, indent=4)
    logger.info("Finished writing data files to {}".format(options.output))


def get_summary_command(options):
    import json
    logger.info("Getting summary for study %s. Writing to %s.",
                options.study_id, options.output.name)

    summary = get_study_variable_summary(options.study_id)
    print('summary: ', list(summary))
    if summary is not None:
        json.dump(summary, options.output, indent=4)
        logger.debug("Summary dumped")
    else:
        raise RuntimeError("Error getting study summary")


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
        sys.exit(0)
    except Exception as e:
        logger.exception(e)
        logger.error(e)
        sys.exit(e.code if hasattr(e, "code") else 99)