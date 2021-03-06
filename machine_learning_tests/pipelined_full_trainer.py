import configparser
import pickle
import sys
from timeit import default_timer
import numpy as np
from random import shuffle
from itertools import chain
from math import floor

from sklearn.externals import joblib
from sklearn.naive_bayes import MultinomialNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC, LinearSVC
from sklearn.model_selection import GridSearchCV, cross_val_score, StratifiedKFold
from sklearn.preprocessing import Normalizer
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer

try:
    from machine_learning_tests import helper_functions as helpers
except ModuleNotFoundError:
    import helper_functions as helpers

if __name__ == "__main__":
    max_feats = 10000
    # Read in ini formatted config file passed as command line argument, replace path shortening variables
    config = configparser.ConfigParser()
    config.read(sys.argv[1])
    arguments = config[sys.argv[2]]
    print(sys.argv[2])
    pre_dispath = 1
    for key in arguments:
        arguments[key] = helpers.replace_pathvar_with_environ(arguments[key])
    # Extract triple of arrays from pickled docs, use doc_id for bag of words, fv_array for doc_prop vector    
    labels, fv_array, doc_ids = pickle.load(open(arguments["feature_vector"], "rb"))
    print([len(x) for x in (labels, fv_array, doc_ids)], flush=True)
    print(labels[:5], fv_array[:5], doc_ids[:5], sep="\n", flush=True)
    # If ini specifies to use less than all documents, take a random sample of the zero terms
    if arguments["training_doc_count"] != "ALL":
        shuffle_size = None
        one_tuples = []
        zero_tuples = []
        shuffle_size_too_big = False
        # Split fvs and doc ids by label
        for i in range(len(labels)):
            if labels[i]:
                one_tuples.append((labels[i], fv_array[i], doc_ids[i]))
            else:
                zero_tuples.append((labels[i], fv_array[i], doc_ids[i]))
        # do nothing if the doc_count is a multiplier and requested size greater than total zeroes
        if arguments["training_doc_count"].startswith("x"):
            if int(arguments["training_doc_count"][1:]) * len(one_tuples) >= len(zero_tuples):
                shuffle_size_too_big = True
            else:
                shuffle_size = int(arguments["training_doc_count"][1:]) * len(one_tuples)
        # Do nothing if doc_count is a percent >= 100
        elif arguments["training_doc_count"].endswith("PER"):
            if (int(arguments["training_doc_count"][:-3]) / 100) * len(zero_tuples) >= len(zero_tuples):
                shuffle_size_too_big = True
            else:
                shuffle_size = (int(arguments["training_doc_count"][:-3]) / 100) * len(zero_tuples)
        else:
            # do nothing if requested size bigger than total zeroes
            shuffle_size = int(arguments["training_doc_count"])
            if shuffle_size >= len(zero_tuples):
                shuffle_size_too_big = True
        # Cut down zero tuples to random size desired
        if not shuffle_size_too_big:
            shuffle(zero_tuples)
            shuffle_size = floor(shuffle_size)
            zero_tuples = zero_tuples[:shuffle_size]
            # Reassign labels in ordered sequence and assign fvs and doc ids while maintaining pairings
            labels = [item[0] for item in chain(one_tuples, zero_tuples)]
            fv_array = [item[1] for item in chain(one_tuples, zero_tuples)]
            doc_ids = [item[2] for item in chain(one_tuples, zero_tuples)]
            # print(len(zero_tuples), zero_tuples[:5])
            # print(len(one_tuples), one_tuples[:5])
            # print(labels)
            # print(fv_array[:5])
            # print(doc_ids[:5])
    parameters = {}
    pipeline_input = []
    # Select between training method, set parameters and pipeline input for each option
    if arguments["training_method"] == "BOW":
        print((1, 1) if arguments.getboolean("1gram") else (1, 3), flush=True)
        start = default_timer()
        transf = TfidfVectorizer(
            input="filename",
            strip_accents="unicode",
            ngram_range=(1, 1) if arguments.getboolean("1gram") else (1, 3),
            stop_words="english",
            max_df=0.85,
            norm="l1",
            sublinear_tf=True,
            max_features=max_feats,
        )
        features = transf.fit_transform([arguments["document_path"] + idx + ".txt" for idx in doc_ids])
        print(str((default_timer() - start) / 60), flush=True)
        # pipeline_input.append(("tfidf_vect", TfidfVectorizer()))
        # parameters.update({
        #     "tfidf_vect__strip_accents": [None, "unicode"],
        #     "tfidf_vect__ngram_range": [(1, 1), (1, 2), (1, 3)],
        #     "tfidf_vect__stop_words": [None, "english"],
        #     "tfidf_vect__max_df": [x / 10 for x in range(2, 11, 2)],
        #     "tfidf_vect__norm": ["l1"],
        #     "tfidf_vect__sublinear_tf": [True],
        #     "tfidf_vect__min_df": [0.15],
        # })
    elif arguments["training_method"] == "DOCPROP":
        transf = Normalizer(norm='l1')
        features = transf.fit_transform(np.array(fv_array))
        # pipeline_input.append(("pre", Normalizer()))
        # parameters.update({
        #     "pre__norm": ["l1", "l2", "max"]
        # })
    else:
        raise ValueError("Invalid training_method argument specified in config")
    # Select among classifiers and set their parameters for GridSearchCV
    if arguments["classifier"] == "SVM":
        clf = SVC()
        parameters.update({
                "clf__coef0": [0.5],
                "clf__cache_size": [10000],
                "clf__degree": [3],
                "clf__class_weight": ["balanced"],
                "clf__C": [1.0],
                # "clf__degree": [1, 2, 3],
                "clf__kernel": ["rbf"],
                # "clf__class_weight": ["balanced", None],
        })
    elif arguments["classifier"] == "MNNB":
        clf = MultinomialNB()
        parameters.update({
            "clf__alpha": [0, 1.0, 0.1, 10.0, 5.0],
            "clf__fit_prior": [True, False],
        })
    elif arguments["classifier"] == "KNN":
        clf = KNeighborsClassifier()
        parameters.update({
            "clf__n_neighbors": [3, 5, 10],
            "clf__weights": ["uniform", "distance"],
            "clf__algorithm": ["ball_tree", "kd_tree", "brute"],
            "clf__p": [1, 2, 3, 4],
            "clf__n_jobs": [-1],
        })
    elif arguments["classifier"] == "LSVM":
        clf = LinearSVC()
        parameters.update({
            "clf__penalty": ["l1", "l2"],
            "clf__loss": ["hinge", "squared_hinge"],
            "clf__fit_intercept": [False, True],
            "clf__C": [0.01, 0.1, 1.0, 10.0, 100.0],
            # makes dual True if num samples is lequal to num features, false otherwise
            "clf__dual": [features.shape[0] <= features.shape[1]],
            "clf__class_weight": ["balanced", None],
        })
    else:
        raise ValueError("unsupported classifier argument given")
    print(features.shape[0], features.shape[1])
    pipeline_input.append(("clf", clf))
    pipe = Pipeline(pipeline_input)
    print(pipe, pipeline_input, parameters, sep="\n")
    start = default_timer()
    inner_cv = StratifiedKFold(shuffle=True)
    outer_cv = StratifiedKFold(shuffle=True)
    grid_search = GridSearchCV(
        estimator=pipe,
        param_grid=parameters,
        cv=inner_cv,
        scoring="roc_auc",
        n_jobs=-1,
        verbose=2,
        pre_dispatch=pre_dispath,
        error_score=-1
    )
    grid_search.fit(features, labels)
    nested_score = cross_val_score(
        estimator=clf,
        X=features,
        y=labels,
        cv=outer_cv,
        scoring="roc_auc",
        n_jobs=1,
    )
    print(grid_search, grid_search.best_estimator_, sep="\n")
    print(str((default_timer() - start) / 60))
    print(grid_search.best_score_, nested_score.mean(), grid_search.best_score_ - nested_score.mean(), sep=", ")
    print(grid_search.best_params_)
    joblib.dump((grid_search, transf), arguments["classifier_path"] + sys.argv[2]
                + ("_{}feats".format(max_feats) if max_feats != -1 else "") + ".joblib")
