import pickle
from sklearn.externals import joblib
import configparser
import sys
from multiprocessing import Pool
import numpy as np

try:
    from machine_learning_tests import helper_functions as helpers
except ModuleNotFoundError:
    import helper_functions as helpers


def docprop_ranking(param_tup):
    features = param_tup[1].transform(param_tup[0][1].reshape(1, -1))
    try:
        return param_tup[0][0], param_tup[2].predict_proba(features)[0][1], param_tup[2].predict(features)
    except AttributeError:
        return param_tup[0][0], param_tup[2].decision_function(features)[0], param_tup[2].predict(features)


def bow_ranking(param_tup):
    features = param_tup[1].transform([arguments["document_path"] + param_tup[0] + ".txt"])
    try:
        return param_tup[0][0], param_tup[2].predict_proba(features)[0][1], param_tup[2].predict(features)
    except AttributeError:
        return param_tup[0][0], param_tup[2].decision_function(features)[0], param_tup[2].predict(features)

if __name__ == "__main__":
    config = configparser.ConfigParser()
    config.read(sys.argv[1])
    arguments = config[sys.argv[2]]
    for key in arguments:
        arguments[key] = helpers.replace_pathvar_with_environ(arguments[key])
    canon_to_id = pickle.load(
        open(
            helpers.replace_pathvar_with_environ("$STORE/kinase_canonical_to_nxtprot_id.pkl"), "rb"
        )
    )
    classifier, transformer = joblib.load(arguments["classifier_path"])
    print(classifier)
    print(transformer)
    with open(arguments["out_path"], "w") as outfile:
        in_dict = pickle.load(open(arguments["possible_matches"], "rb"))
        print(in_dict)
        if arguments["training_method"] == "BOW":
            for kinase, doc_set in in_dict.items():
                with Pool() as p:
                    result = p.map(bow_ranking, [(doc, transformer, classifier) for doc in doc_set])
                result = sorted(result, reverse=True, key=lambda x: x[1])
                count = 0
                for item in result:
                    if count == 30 or (item[2] == 0 and count > 15):
                        break
                    count += 1
                    outfile.write(
                        " ".join(
                            [
                                canon_to_id[kinase],
                                "dummy", item[0],
                                str(count),
                                str(round(item[1] * 100, 2)),
                                arguments["run_id"],
                                "\n"
                            ]
                        )
                    )
        else:
            for kinase, values in in_dict.items():
                doc_set = [(value[0], np.array(value[1:] + [0, 0])) for value in values]
                print(doc_set)
                with Pool() as p:
                    result = p.map(docprop_ranking, [(val, transformer, classifier) for val in doc_set])
                result = sorted(result, reverse=True, key=lambda x: x[1])
                count = 0
                for item in result:
                    if count == 30 or item[2] == 0:
                        break
                    count += 1
                    outfile.write(
                        " ".join(
                            [
                                canon_to_id[kinase],
                                "dummy", item[0],
                                str(count),
                                str(round(item[1] * 100, 2)),
                                arguments["run_id"],
                                "\n"
                            ]
                        )
                    )

