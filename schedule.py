#!/usr/bin/env python
#
# Helper script which given a alisw repository and a alisw.github.io decides
# which builds to schedule based on a set of rules found in config.yaml. 
#
# Things are done this way so that the process of starting a new build is
# always expressed as moving from one state where some builds are missing to a
# state where all the builds that can be built are built. This is different
# from the past approach where people were asking for "please build a new
# release", this is more "build all releases which are missing".
#
# This script is meant to be executed  by jenkins and will output a series of
# property files which can be to drive the actual builds.
import yaml
from argparse import ArgumentParser
from os.path import exists, basename
from os import makedirs, symlink, unlink
from sys import exit
from commands import getstatusoutput
import re
import logging
from logging import debug
from glob import glob

def format(s, **kwds):
  return s % kwds

def decide(done_tags, all_tags, rules):
  to_be_processed = []
  for tag in all_tags:
    if tag in done_tags:
      print "Tag %s was already processed. Skipping" % tag
      continue
    for rule in rules:
      if "exclude" in rule:
        m = re.match(rule["exclude"], tag)
        if m:
          debug("%s excluded by %s" % (tag, rule["exclude"]))
          break
      elif "include" in rule:
        m = re.match(rule["include"], tag)
        payload = {
           "tag": tag,
           "architecture": rule["architecture"]
        }
        if not m:
          continue
        if str(payload) in done_tags:
          continue
        to_be_processed.append(payload)
      else:
        print "Bad rule found. Exiting"
        exit(1)
  return to_be_processed

def extractTuples(name):
  possible_archs = ["(slc.*_x86-64)-(.*)[.]ini",
                    "(ubuntu_x86-64)-(.*)[.]ini",
                    "(osx.*_x86-64)-(.*)[.]ini"]
  for attempt in possible_archs:
    m = re.match(attempt, name)
    if not m:
      continue
    return dict(zip(["architecture", "tag"], m.groups()))

if __name__ == "__main__":
  logging.basicConfig()
  debug("foo")

  parser = ArgumentParser()
  parser.add_argument("--aliroot-repo", dest="aliroot", help="Location of aliroot checkout area")
  parser.add_argument("--alisw-repo", dest="alisw", help="Location of alisw.github.io checkout area")
  parser.add_argument("--dry-run", "-n", action="store_true", dest="dryRun", default=False,
                      help="Just print out what you will do. Do not execute.")
  args = parser.parse_args()
  if not args.aliroot or not exists(args.aliroot):
    parser.error("Please specify where to find aliroot")
  if not args.alisw or not exists(args.alisw):
    parser.error("Please specify where to find alisw.github.io")

  cmd = format("(cd %(repo)s && git tag 2>&1)",
               repo=args.aliroot)
  err, out = getstatusoutput(cmd)
  if err:
    print "Unable to get ALIROOT tags"
    print out
    exit(1)

  # There are three entries in the script:
  #
  # done_tags: the tags which have already been scheduled for build.
  # all_tags: all the tags available
  # rules: the rules which specify which tags need to be scheduled and using
  #        which version of the recipes.
  done_tags = glob("%s/data/scheduled/*.ini" % args.alisw)
  done_tags = set(str(extractTuples(basename(x))) for x in done_tags)
  print done_tags
  all_tags = out.split("\n")
  rules = yaml.load(file("config.yaml"))

  specs = decide(done_tags, all_tags, rules)
  if not specs:
    print "No tags to be processed"
    exit(0)
  print "Tags to be scheduled:\n" + "\n".join(str(x) for x in specs)

  if args.dryRun:
    print "Dry run specified, not running."
    exit(0)

  # We create the spec in a subdirectory "specs", so that we can always know
  # what were the options used to build a given release. We then copy them in
  # the local area, so that jenkins can use it to schedule other jobs.
  for s in specs:
    getstatusoutput("mkdir -p %s/data/scheduled" % args.alisw)
    p = format("%(alisw)s/data/scheduled/%(architecture)s-%(tag)s.ini",
               alisw=args.alisw,
               architecture=s["architecture"],
               tag=s["tag"])
    f = file(p, "w")
    f.write("ARCHITECTURE=%s\n" % s["architecture"])
    f.close()
    unlink(basename(p))
    symlink(p, basename(p))