#!/usr/bin/env python3

import argparse
import os
import re
import requests
import sys

QUAYBASE = "https://quay.ceph.io/api/v1"
REPO = "ceph-ci/ceph"

# cache shaman search results so we only have to ask once
short_sha1_cache = set()
sha1_cache = set()

# quay page ranges to fetch; hackable for testing
start_page = 1
page_limit = 100000

NAME_RE = re.compile(
    r'(.*)-([0-9a-f]{7})-centos-([78])-(x86_64|aarch64)-devel'
)
SHA1_RE = re.compile(r'([0-9a-f]{40})(-crimson|-aarch64)*')


def get_all_quay_tags(quaytoken):
    page = start_page
    has_additional = True
    ret = []

    while has_additional and page < page_limit:
        try:
            response = requests.get(
                '/'.join((QUAYBASE, 'repository', REPO, 'tag')),
                params={'page': page, 'limit': 100, 'onlyActiveTags': 'false'},
                headers={'Authorization': f'Bearer {quaytoken}'},
                timeout=30,
            )

            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(
                'Quay.io request',
                response.url,
                'failed:',
                e,
                requests.reason,
                file=sys.stderr
            )
            break
        response = response.json()
        ret.extend(response['tags'])
        page += 1
        has_additional = response.get('has_additional')
    return ret


def parse_quay_tag(tag):

    mo = NAME_RE.match(tag)
    if mo is None:
        return None, None, None, None
    ref = mo.group(1)
    short_sha1 = mo.group(2)
    el = mo.group(3)
    arch = mo.group(4)
    return ref, short_sha1, el, arch


def query_shaman(ref, sha1, el):

    params = {
        'project': 'ceph',
        'flavor': 'default',
        'status': 'ready',
        'distros': 'centos/{el}/x86_64,centos/{el}/aarch64'.format(el=el)
        if el
        else 'centos/7/x86_64,centos/8/x86_64,centos/9/x86_64,'
        + 'centos/7/aarch64,centos/8/aarch64,centos/9/aarch64',
    }

    if ref:
        params['ref'] = ref
    if sha1:
        params['sha1'] = sha1
    try:
        response = requests.get(
            'https://shaman.ceph.com/api/search/',
            params=params,
            timeout=30
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(
            'Shaman request',
            response.url,
            'failed:',
            e,
            response.reason,
            file=sys.stderr
        )
    return response


def ref_present_in_shaman(ref, short_sha1, el, arch, verbose):

    if ref is None:
        return False

    if short_sha1 in short_sha1_cache:
        if verbose:
            print(f'Found {short_sha1} in shaman short_sha1_cache')
        return True

    response = query_shaman(ref, None, el)
    if not response.ok:
        print('Shaman request', response.request.url, 'failed:',
              response.status_code, response.reason, file=sys.stderr)
        # don't cache, but claim present:
        # avoid deletion in case of transient shaman failure
        if verbose:
            print(f'Found {ref} (assumed because shaman request failed)')
        return True

    matches = response.json()
    if len(matches) == 0:
        return False
    for match in matches:
        if match['sha1'][:7] == short_sha1:
            if verbose:
                print(f"Found {ref} in shaman: sha1 {match['sha1']}")
            short_sha1_cache.add(short_sha1)
            return True
    return False


def sha1_present_in_shaman(sha1, verbose):

    if sha1 in sha1_cache:
        if verbose:
            print(f'Found {sha1} in shaman sha1_cache')
        return True

    response = query_shaman(None, sha1, None)
    if not response.ok:
        print('Shaman request', response.request.url, 'failed:',
              response.status_code, response.reason, file=sys.stderr)
        # don't cache, but claim present
        # to avoid deleting on transient shaman failure
        if verbose:
            print(f'Found {sha1} (assuming because shaman request failed)')
        return True

    matches = response.json()
    if len(matches) == 0:
        return False
    for match in matches:
        if match['sha1'] == sha1:
            if verbose:
                print(f'Found {sha1} in shaman')
            sha1_cache.add(sha1)
            return True
    return False


def delete_from_quay(tagname, quaytoken, dryrun):
    if dryrun:
        print('Would delete from quay:', tagname)
        return

    try:
        response = requests.delete(
            '/'.join((QUAYBASE, 'repository', REPO, 'tag', tagname)),
            headers={'Authorization': f'Bearer {quaytoken}'},
            timeout=30,
        )

        response.raise_for_status()
        print('Deleted', tagname)
    except requests.exceptions.RequestException as e:
        print(
            'Problem deleting tag %s:',
            tagname,
            e,
            response.reason,
            file=sys.stderr
        )


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--dryrun', action='store_true',
                        help="don't actually delete")
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="say more")
    return parser.parse_args()


def main():
    args = parse_args()

    quaytoken = None
    if not args.dryrun:
        if 'QUAYTOKEN' in os.environ:
            quaytoken = os.environ['QUAYTOKEN']
        else:
            quaytoken = open(
                os.path.join(os.environ['HOME'], '.quaytoken'),
                'rb'
            ).read().strip().decode()

    quaytags = get_all_quay_tags(quaytoken)

    # find all full tags to delete, put them and ref tag on list
    tags_to_delete = set()
    short_sha1s_to_delete = []
    for tag in quaytags:
        name = tag['name']
        if 'expiration' in tag or 'end_ts' in tag:
            if args.verbose:
                print(f'Skipping deleted-or-overwritten tag {name}')
            continue

        ref, short_sha1, el, arch = parse_quay_tag(name)
        if ref is None:
            if args.verbose:
                print(f'Skipping {name}, not in ref-shortsha1-el-arch form')
            continue

        if ref_present_in_shaman(ref, short_sha1, el, arch, args.verbose):
            if args.verbose:
                print(f'Skipping {name}, present in shaman')
            continue

        # accumulate full and ref tags to delete; keep list of short_sha1s

        if args.verbose:
            print(f'Marking {name} for deletion')
        tags_to_delete.add(name)
        if ref:
            # the ref tag may already have been overwritten by a new
            # build of the same ref, but a different sha1. Delete it only
            # if it refers to the same image_id as the full tag.
            names_of_same_image = [
                t['name'] for t in quaytags
                if not t['is_manifest_list']
                and t['image_id'] == tag['image_id']
            ]
            if args.verbose:
                if ref in names_of_same_image:
                    print(f'Marking {name} for deletion')
                    tags_to_delete.add(name)
                else:
                    print(f'Skipping {name}: not in {names_of_same_image}')
        if short_sha1:
            if args.verbose:
                print(f'Marking {short_sha1} for 2nd-pass deletion')
            short_sha1s_to_delete.append(short_sha1)

    # now find all the full-sha1 tags to delete by making a second
    # pass and seeing if the tagname starts with a short_sha1 we
    # know we want deleted, or if it matches SHA1_RE but is gone from
    # shaman
    for tag in quaytags:

        name = tag['name']
        if 'expiration' in tag or 'end_ts' in tag:
            continue

        if name[:7] in short_sha1s_to_delete:
            if args.verbose:
                print(f'Marking {name} for deletion: matches short_sha1 {name[:7]}')

            tags_to_delete.add(name)
            # already selected a SHA1 tag; no point in checking for orphaned
            continue

        if match := SHA1_RE.match(name):
            sha1 = match[1]
            if sha1_present_in_shaman(sha1, args.verbose):
                if args.verbose:
                    print(f'Skipping {name}, present in shaman')
                continue
            if args.verbose:
                print(
                    'Marking %s for deletion: orphaned sha1 tag' % name
                )
            tags_to_delete.add(name)

    if args.verbose:
        print('\nDeleting tags:', sorted(tags_to_delete))

    # and now delete all the ones we found
    for tagname in sorted(tags_to_delete):
        delete_from_quay(tagname, quaytoken, args.dryrun)


if __name__ == "__main__":
    sys.exit(main())
