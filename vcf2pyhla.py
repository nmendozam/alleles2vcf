import argparse
import re
from collections import defaultdict
from typing import List

import pandas as pd

"""
To generate the input file from the imputation run this command
> grep "#CHR" IMPUTED.vcf > HLA.vcf
> grep "HLA_" IMPUTED.vcf >> HLA.vcf
"""


def read_vcf(file_name):
    """
    This takes a vcf file data frame and returns
    a table were the row indexes are the allele names
    and the column names are the sample names
    """
    df = pd.read_csv(file_name, sep="\t", on_bad_lines="warn")
    # Use alleles as index
    df["ID"] = df["ID"].str.replace("HLA_", "")
    df.set_index("ID", inplace=True)
    # Drop non sample columns
    df.drop(
        ["#CHROM", "POS", "REF", "ALT", "QUAL", "FILTER", "INFO", "FORMAT"],
        axis=1,
        inplace=True,
    )
    return df


class AlleleList:
    def __init__(self, alleles: pd.DataFrame) -> None:
        self.df = pd.DataFrame(alleles)
        self.df["scores"] = alleles.str.extract(":(([0-9]*[.])?[0-9]+):")[0].apply(
            pd.to_numeric
        )
        self.df["is_homozygous"] = alleles.str.contains("1\|1")
        self.df["is_high_res"] = self.find_high_res(alleles.index.values.tolist())

        genes = self.get_genes(self.df.index)
        self.df = self.df.set_index([genes, self.df.index]).rename_axis(
            ["gene", "allele"]
        )

    def find_high_res(self, allele_list: List[str]):
        """
        Checks wether the alleles is covered by a higher resolution one
        or not. Because the imputation returns multiple levels of resolutions
        eg.  ['A*02', 'A*02:01:01:01' ] returns [False, True]
        """
        high_res = list()
        for i, x in enumerate(allele_list):
            # cross comparison with every other allele
            comp = [x in y for y in allele_list]
            comp[i] = False  # remove self comparison
            high_res.append(not any(comp))

        return high_res

    def get_genes(self, alleles: pd.Series):
        return alleles.str.extract(r"([A-Z0-1]+?)\*")[0]

    def sort_and_fill(self):
        results = list()
        genes = self.df.index.get_level_values("gene").unique()
        for gene in sorted(genes):
            alleles = self.df.loc[[gene]].reset_index(level=0)

            homozygous = alleles.loc[alleles.is_homozygous & alleles.is_high_res]
            # Check allele by side
            # TODO: check allele side there might be to options for the same side with higher score that the other side
            allele = alleles.loc[alleles.is_high_res].nlargest(2, columns="scores")

            to_append = list()
            if homozygous.count()[0] == 1:
                to_append = homozygous.index.tolist() * 2
            elif allele.count()[0] == 2:
                to_append = allele.index.tolist()
            elif allele.count()[0] == 1:
                to_append = allele.index.tolist() + ["NA"]

            results.extend(to_append)

        return results


def get_true_alleles(vcf):
    vcf = read_vcf(vcf)
    true_alleles = dict()
    for sample in vcf.columns:
        # Get the list of alleles for that column(sample)
        alleles = vcf.loc[~vcf[sample].str.contains("0\|0", na=False), sample]
        true_alleles[sample] = AlleleList(alleles).sort_and_fill()
    return true_alleles


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert vcf file to pyhla and output to std out"
    )
    parser.add_argument("vcf", type=str, help="input vcf file name")
    parser.add_argument("--phe", type=str, help="input phe file name", default="")

    args = parser.parse_args()

    if args.phe:
        phe = pd.read_csv(args.phe, sep=" ", comment="##")
        phe.set_index("IID", inplace=True)

    true_alleles = get_true_alleles(args.vcf)
    for key in true_alleles:
        phenotype = 1
        if args.phe:
            phenotype = int(phe.loc[[key]].LLI)
        print(key, phenotype, "\t".join(true_alleles[key]), sep="\t")