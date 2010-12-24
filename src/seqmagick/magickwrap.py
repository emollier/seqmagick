"""
@author: bhodges
"""

import os
import itertools
import re
import subprocess
import sys
import string

from Bio import SeqIO
from Bio.Alphabet import IUPAC
from Bio.Align.Applications import MuscleCommandline
from Bio.Seq import Seq, SeqRecord
from Bio.SeqUtils.CheckSum import seguid
from Bio.SeqIO import FastaIO
#from numpy import *
from fileformat import FileFormat


class MagickWrap(object):
    """
    A class that wraps functionality present in BioPython.    
    """

    def __init__(self, tmp_dir, in_files, out_file=None, alphabet=None, debug=False, verbose=False):
        """
        Constructor
        """
        self.source_files = in_files
        self.tmp_dir = tmp_dir
        self.destination_file = out_file
        self.debug = debug
        self.verbose = verbose
            

# Public Methods


    def convert_format(self):
        """
        Convert input file to a different output format.  This will not work for all formats, 
        e.g. going from fastq to fasta or going from a non-alignment fasta file to phylip would not work.  
        Converts only the first file in the source_files list.
        """
        source_file = self.source_files[0]
        source_file_type = FileFormat.lookup_file_type(os.path.splitext(source_file)[1])
        destination_file = self.destination_file
        destination_file_type = FileFormat.lookup_file_type(os.path.splitext(destination_file)[1])
   
        if source_file == destination_file:
            raise Exception, "source_file and destination_file cannot be the same file."
        
        if self.destination_file is not None:
           SeqIO.convert(source_file, source_file_type, destination_file, destination_file_type) 
        else:
            raise Exception, "An output file was not specified.  Required by the convert action."
        pass


    def translate_sequences(self):
        """

        """
        pass


    def is_strict_alphabet(self):
        """

        """
        pass


    def create_muscle_alignment(self):
        """
        Use BioPython muscle wrapper to create an alignment.
        """
        muscle_command = MuscleCommandline(input=self.source_files[0], out=self.destination_file)
        if self.debug: print 'DEBUG: muscle command:\n' + str(muscle_command)
        child = subprocess.Popen(str(muscle_command),
                                 stdin=None,
                                 stdout=None,
                                 stderr=None,
                                 shell=(sys.platform!="win32"))
       	return_code = child.wait()
       	return return_code
        
    def transform(self, cut=False, dashgap=False, ungap=False, lower=False, 
                  reverse=False, strict=False, translate=False, upper=False, linewrap=False, 
                  first_name_capture=False, deduplicate_sequences=False, deduplicate_taxa=False, 
                  reverse_complement=False, pattern_include=False, pattern_exclude=False,
                  squeeze=False, head=False, tail=False):
        """
        This method wraps many of the transformation generator functions found 
        in this class.
        """

        for source_file in self.source_files: 
            # Get just the file name, useful for naming the temporary file.
            file_name = os.path.split(source_file)[1]
            source_file_type = FileFormat.lookup_file_type(os.path.splitext(source_file)[1])

            # Specify full path to temporary file for operations that require this.
            # tmp_file will have a seqmagick prefix, i.e. /tmp/seqmagick.a.fasta.  
            # If destination_file is part of the magickwrap instance, use that insted.
            destination_file = os.path.join(self.tmp_dir, 'seqmagick.' + file_name) 
            if self.destination_file is not None:
                destination_file = self.destination_file

            destination_file_type = FileFormat.lookup_file_type(os.path.splitext(destination_file)[1])

            # Get an iterator.
            records = SeqIO.parse(source_file, source_file_type)

            #########################################
            # Apply generator functions to iterator.#
            #########################################

            if self.verbose: print 'Setting up generator functions for file: ' + source_file

            # Deduplication occurs first, to get a checksum of the 
            # original sequence and to store the id field before any 
            # transformations occur.
     
            if deduplicate_sequences:
                records = self._deduplicate_sequences(records)

            if deduplicate_taxa:
                records = self._deduplicate_taxa(records)

            if dashgap:
                records = self._dashes_cleanup(records)        


            if first_name_capture:
                records = self._first_name_capture(records)
            if upper:
                records = self._upper_sequences(records)
              
            if lower:
                records = self._lower_sequences(records)

            if reverse:
                records = self._reverse_sequences(records)

            if reverse_complement:
                records = self._reverse_complement_sequences(records)
  
            if ungap:
                records = self._ungap_sequences(records)

            if pattern_include:
                records = self._name_include(records, pattern_include)

            if pattern_exclude:
                records = self._name_exclude(records, pattern_exclude)

            if head and tail:
                raise Exception, "Error: head and tail are mutually exclusive at the moment."

            if head:
                records = self._head(records, head)

            if tail:
                # To know where to begin including records for tail, we need to count 
                # the total number of records, which requires going through the entire 
                # file and additional time.
                record_count = sum(1 for record in SeqIO.parse(source_file, source_file_type))
                records = self._tail(records, tail, record_count)


            if squeeze:
                if self.verbose: print 'Performing squeeze, which requires a new iterator for the first pass.'
                gaps = []
                # Need to iterate an additional time to determine which 
                # gaps are share between all sequences in an alignment.
                for record in SeqIO.parse(source_file, source_file_type):
                    # Use numpy to prepopulate a gaps list.
                    if len(gaps) == 0:
                        gaps_length = len(str(record.seq))
                        #gaps = list(ones( (gaps_length), dtype=int16 ))
                        gaps = [1] * gaps_length
                    gaps = map(self._gap_check, gaps, list(str(record.seq)))
                records = self._squeeze(records, gaps)
                if self.verbose: print 'List of gaps to remove for alignment created by squeeze.'
                if self.debug: print 'DEBUG: squeeze gaps list:\n' + str(gaps)

            # cut needs to go after squeeze or the gaps list will no longer be relevent.  
            # It is probably best not to use squeeze and cut together in most cases.
            if cut:
                records = self._cut_sequences(records, start=cut[0], end=cut[1])

           # Only the fasta format is supported, as SeqIO.write does not hava a 'wrap' parameter.
            if linewrap is not None and destination_file_type == 'fasta' and source_file_type == 'fasta':
                if self.verbose: print 'Attempting to write out fasta file with linebreaks set to ' + str(linewrap) + '.'
                with open(destination_file,"w") as handle:
                    writer = FastaIO.FastaWriter(handle, wrap=linewrap)
                    writer.write_file(records)
            else:
            # Mogrify requires writing all changes to a temporary file by default, 
            # but convert uses a destination file instead if one was specified. Get
            # sequences from an iterator that has generator functions wrapping it. 
            # After creation, it is then copied back over the original file if all 
            # tasks finish up without an exception being thrown.  This avoids 
            # loading the entire sequence file up into memory.
                if self.verbose: print 'Read through iterator and write out transformations to file: ' + destination_file
                SeqIO.write(records, destination_file, destination_file_type)

            # Overwrite original file with temporary file, if necessary.
            if self.destination_file is None:
                if self.verbose: print 'Moving temporary file: ' + destination_file + ' back to file: ' + source_file
                os.rename(destination_file, source_file)



# Private Methods 


    # Generator Functions
 
    def _dashes_cleanup(self, records):
        """
        Take an alignment and convert any undesirable characters such as ? or ~ to -.
        """
        if self.verbose: print 'Applying _dashes_cleanup generator: ' + \
                               'converting any ? or ~ characters to -.'
        translation_table = string.maketrans("?~", "--")
        for record in records:
            yield SeqRecord(Seq(str(record.seq).translate(translation_table)), 
                            id=record.id, description=record.description)


    def _deduplicate_sequences(self, records):
        """
        Remove any duplicate records with identical sequences, keep the first 
        instance seen and discard additional occurences.
        """
        if self.verbose: print 'Applying _deduplicate_sequences generator: ' + \
                               'removing any duplicate records with identical sequences.'
        checksums = set()
        for record in records:
            checksum = seguid(record.seq)
            if checksum in checksums:
                continue
            checksums.add(checksum)
            yield record

             
    def _deduplicate_taxa(self, records):
        """
        Remove any duplicate records with identical IDs, keep the first 
        instance seen and discard additional occurences.
        """
        if self.verbose: print 'Applying _deduplicate_taxa generator: ' + \
                               'removing any duplicate records with identical IDs.'
        taxa = set()
        for record in records:
            # Default to full ID, split if | is found.
            taxid = record.id
            if '|' in record.id:
                taxid = int(record.id.split("|")[0])
            if taxid in taxa:
                continue
            taxa.add(taxid)
            yield record


    def _first_name_capture(self, records):
        """
        Take only the first whitespace-delimited word as the name of the sequence.  
        Essentially removes any extra text from the sequence's description.
        """
        if self.verbose: print 'Applying _first_name_capture generator: ' + \
                               'making sure ID only contains the  first whitespace-delimited word.'
        whitespace = re.compile(r'\s+')
        for record in records:
            if whitespace.search(record.description):
                yield SeqRecord(record.seq, id=record.id, 
                                description="")
            else: 
                yield record


    def _cut_sequences(self, records, start, end):
        """
        Cut sequences given a one-based range.  Includes last item.
        """
        if self.verbose: print 'Applying _cut_sequences generator: ' + \
                               'cutting sequences based on specified range (' + start + '-' + end + ').'
        start = start - 1
        for record in records:
            yield SeqRecord(record.seq[start:end], id=record.id, 
                            description=record.description)


    def _lower_sequences(self, records):
        """
        Convert sequences to all lowercase.
        """
        if self.verbose: print 'Applying _lower_sequences generator: ' + \
                               'converting sequences to all lowercase.'
        for record in records:
            yield record.lower()


    def _upper_sequences(self, records):
        """
        Convert sequences to all uppercase.
        """
        if self.verbose: print 'Applying _upper_sequences generator: ' + \
                               'converting sequences to all uppercase.'
        for record in records:
            yield record.upper()


    def _reverse_sequences(self, records):
        """
        Reverse the order of sites in sequences.
        """
        if self.verbose: print 'Applying _reverse_sequences generator: ' + \
                               'reversing the order of sites in sequences.'
        for record in records:
            yield SeqRecord(record.seq[::-1], id=record.id,
                            description=record.description)


    def _reverse_complement_sequences(self, records):
        """
        Transform sequences into reverse complements.
        """
        if self.verbose: print 'Applying _reverse_complement_sequences generator: ' + \
                               'transforming sequences into reverse complements.'
        for record in records:
            yield SeqRecord(record.seq.reverse_complement(), id=record.id,
                            description=record.description)


    def _ungap_sequences(self, records):
        """
        Remove gaps from sequences, given an alignment.
        """
        if self.verbose: print 'Applying _ungap_sequences generator: ' + \
                               'removing gaps from the alignment.'
        for record in records:
            yield SeqRecord(record.seq.ungap("-"), id=record.id,
                            description=record.description)


    def _name_include(self, records, filter_regex):
        """
        Given a set of sequences, filter out any sequences with names 
        that do not match the specified regular expression.  Ignore case.
        """
        if self.verbose: print 'Applying _name_include generator: ' + \
                               'including only IDs matching ' + filter_regex + ' in results.'
        regex = re.compile(filter_regex, re.I)
        for record in records:
            if regex.search(record.id):
                yield record
            else: 
                continue


    def _name_exclude(self, records, filter_regex):
        """
        Given a set of sequences, filter out any sequences with names 
        that match the specified regular expression.  Ignore case.
        """
        if self.verbose: print 'Applying _name_exclude generator: ' + \
                               'excluding IDs matching ' + filter_regex + ' in results.'
        regex = re.compile(filter_regex, re.I)
        for record in records:
            if not regex.search(record.id):
                yield record
            else: 
                continue

    def _head(self, records, head):
        """
        Limit results to the top N records.
        """
        if self.verbose: print 'Applying _head generator: ' + \
                               'limiting results to top ' + str(head) + ' records.'
        count = 0
        for record in records:
            if count < head:
                count += 1
                yield record 
            else:
                break


    def _tail(self, records, tail, record_count):
        """
        Limit results to the bottom N records.
        """
        if self.verbose: print 'Applying _tail generator: ' + \
                               'limiting results to bottom ' + str(tail) + ' records.'
        position = 0
        start = record_count - tail
        for record in records:
            if position < start:
                position += 1
                continue
            else:
                yield record


    def _squeeze(self, records, gaps):
        """
        Remove any gaps that are present in the same position across all sequences in an alignment.
        """
        if self.verbose: print 'Applying _squeeze generator: ' + \
                               'removing any gaps that are present ' + \
                               'in the same position across all sequences in an alignment.'
        sequence_length = len(gaps)
        for record in records:
            sequence = list(str(record.seq))
            squeezed = []
            position = 0
            while (position < sequence_length):
                if bool(gaps[position]) is False:
                    squeezed.append(sequence[position])
                position += 1            
            yield SeqRecord(Seq(''.join(squeezed)), id=record.id,
                            description=record.description)

    
    # Begin squeeze-related functions

    def _is_gap(self, character):
        """
        """
        if character == '-':
            return 1
        else:
            return 0


    def _gap_check(self, gap, character):
        """
        Build up a gaps list that is used on all sequences 
        in an alignment.
        """
        # Skip any characters that have already been found
        if gap == 0:
            return gap
        return int(bool(gap) & bool(self._is_gap(character)))

    # End squeeze-related functions



