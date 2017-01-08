import asyncio
import math
import os
import logging
import hashlib
import json

import egsinp
from utils import run_command, read_3ddose, copy, remove

logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))


async def simulate(args, templates, i, y):
    source_beamlet = await simulate_source(args, templates['source'], y)
    logger.info('{} - simulated source'.format(i))
    filtered_beamlet = await filter_source(args, templates['filter'], source_beamlet)
    logger.info('{} - simulated filter'.format(i))
    collimated_beamlet = await collimate(args, templates['collimator'], filtered_beamlet)
    logger.info('{} - simulated collimator'.format(i))
    if args.reflect:
        reflected_beamlet = await reflect(collimated_beamlet)
        dose = await asyncio.gather(*[
            simulate_doses(args, templates, reflected_beamlet, i),
            simulate_doses(args, templates, collimated_beamlet, i)
        ])
    else:
        dose = await simulate_doses(args, templates, collimated_beamlet, i)
    result = {
        'source': source_beamlet,
        'filter': filtered_beamlet,
        'collimator': collimated_beamlet,
        'dose': dose,
    }
    logger.info('{} - simulated doses'.format(i))
    return result


async def reflect(original):
    folder = os.path.dirname(original['phsp'])

    md5 = original['hash'].copy()
    md5.update('reflect')
    base = md5.hexdigest()

    beamlet = {
        'egsinp': original['egsinp'],  # note that this is NOT reflected
        'phsp': os.path.join(folder, '{}.egsphsp'),
        'hash': md5
    }
    temp_phsp = os.path.join(folder, '{}.egsphsp1'.format(base))

    if not os.path.exists(beamlet['phsp']):
        remove(temp_phsp)
        await run_command(['beamdpr', 'reflect', '-x', '1', original['phsp'], temp_phsp])
        os.rename(temp_phsp, beamlet['phsp'])

    return beamlet


async def simulate_source(args, template, y):
    folder = os.path.join(args.egs_home, 'BEAM_RFLCT')
    # calculate
    theta = math.atan(y / args.beam_distance)
    cos_x = -math.cos(theta)
    cos_y = math.copysign(math.sqrt(1 - cos_x * cos_x), y)

    # prepare template
    template['uinc'] = cos_x
    template['vinc'] = cos_y

    # hash
    egsinp_str = egsinp.unparse_egsinp(template)
    md5 = hashlib.md5(egsinp_str.encode('utf-8'))
    base = md5.hexdigest()

    # beamlet properties
    beamlet = {
        'egsinp': os.path.join(folder, '{}.egsinp'.format(base)),
        'phsp': os.path.join(folder, '{}.egsphsp'.format(base)),
        'hash': md5
    }
    temp_phsp = os.path.join(folder, '{}.egsphsp1'.format(base))

    if not os.path.exists(beamlet['phsp']):
        # simulate
        remove(temp_phsp)
        with open(beamlet['egsinp'], 'w') as f:
            f.write(egsinp_str)
        command = ['BEAM_RFLCT', '-p', args.pegs4, '-i', os.path.basename(beamlet['egsinp'])]
        await run_command(command, cwd=folder)
        # translate
        await run_command(['beamdpr', 'translate', '-i', temp_phsp, '-y', '({})'.format(y)])
        # rotate
        angle = str(math.pi / 2)
        await run_command(['beamdpr', 'rotate', '-i', temp_phsp, '-a', angle])
        os.rename(temp_phsp, beamlet['phsp'])

    # stats
    command = ['beamdpr', 'stats', '--format=json', beamlet['phsp']]
    beamlet['stats'] = json.loads(await run_command(command))

    return beamlet


async def filter_source(args, template, source_beamlet):
    folder = os.path.join(args.egs_home, 'BEAM_FILTR')
    # prepare template
    template['ncase'] = source_beamlet['stats']['total_particles']
    template['spcnam'] = os.path.join('../', 'BEAM_RFLCT', os.path.basename(source_beamlet['phsp']))

    # hash
    egsinp_str = egsinp.unparse_egsinp(template)
    md5 = source_beamlet['hash'].copy()
    md5.update(egsinp_str.encode('utf-8'))
    base = md5.hexdigest()

    # beamlet properties
    beamlet = {
        'egsinp': os.path.join(folder, '{}.egsinp'.format(base)),
        'phsp': os.path.join(folder, '{}.egsphsp'.format(base)),
        'hash': md5
    }
    temp_phsp = os.path.join(folder, '{}.egsphsp1'.format(base))

    if not os.path.exists(beamlet['phsp']):
        # simulate
        remove(temp_phsp)
        with open(beamlet['egsinp'], 'w') as f:
            f.write(egsinp_str)
        command = ['BEAM_FILTR', '-p', args.pegs4, '-i', os.path.basename(beamlet['egsinp'])]
        await run_command(command, cwd=folder)
        os.rename(temp_phsp, beamlet['phsp'])

    # stats
    command = ['beamdpr', 'stats', '--format=json', beamlet['phsp']]
    beamlet['stats'] = json.loads(await run_command(command))

    return beamlet


async def collimate(args, template, source_beamlet):
    name = 'BEAM_{}'.format(template['title'])
    folder = os.path.join(args.egs_home, name)

    # prepare template
    template['ncase'] = source_beamlet['stats']['total_particles']
    template['spcnam'] = '../BEAM_FILTR/' + os.path.basename(source_beamlet['phsp'])

    # hash
    egsinp_str = egsinp.unparse_egsinp(template)
    md5 = source_beamlet['hash'].copy()
    md5.update(egsinp_str.encode('utf-8'))
    base = md5.hexdigest()

    # beamlet properties
    beamlet = {
        'egsinp': os.path.join(folder, '{}.egsinp'.format(base)),
        'phsp': os.path.join(folder, '{}.egsphsp'.format(base)),
        'hash': md5
    }
    temp_phsp = os.path.join(folder, '{}.egsphsp1'.format(base))

    if not os.path.exists(beamlet['phsp']):
        # simulate
        remove(beamlet['phsp'])
        with open(beamlet['egsinp'], 'w') as f:
            f.write(egsinp_str)
        command = [name, '-p', args.pegs4, '-i', os.path.basename(beamlet['egsinp'])]
        await run_command(command, cwd=folder)
        os.rename(temp_phsp, beamlet['phsp'])

    # stats
    command = ['beamdpr', 'stats', '--format=json', beamlet['phsp']]
    beamlet['stats'] = json.loads(await run_command(command))

    return beamlet


async def simulate_doses(args, templates, beamlet, index):
    context = {
        'egsphant_path': os.path.join(SCRIPT_DIR, args.phantom),
        'phsp_path': beamlet['phsp'],
        'ncase': beamlet['stats']['total_photons'] * (args.dose_recycle + 1),
        'nrcycl': args.dose_recycle,
        'n_split': args.dose_photon_splitting,
        'dsource': args.target_distance,
        'phicol': 90,
        'x': args.target_x,
        'y': args.target_y,
        'z': args.target_z,
        'idat': 1,
        'theta': 180,
    }

    doses = {'arc': []}

    # stationary
    context['phi'] = 0
    egsinp_str = templates['stationary_dose'].format(**context)
    path = os.path.join(args.output_dir, 'dose/stationary/stationary{}.3ddose.npz'.format(index))
    doses['stationary'] = simulate_dose(args, beamlet, egsinp_str, path)

    # arc
    for phimin, phimax in dose_angles(args):
        context['nang'] = 1
        context['phimin'] = phimin
        context['phimax'] = phimax
        egsinp_str = templates['arc_dose'].format(**context)
        path = os.path.join(args.output_dir, 'dose/arc/arc{}_{}_{}.3ddose.npz'.format(index, phimin, phimax))
        doses['arc'].append(simulate_dose(args, beamlet, egsinp_str, path))
    futures = [doses['stationary']] + doses['arc']
    doses['stationary'], *doses['arc'] = await asyncio.gather(*futures)
    return doses


async def simulate_dose(args, beamlet, egsinp_str, path):
    folder = os.path.join(args.egs_home, 'dosxyznrc')
    # hash
    md5 = beamlet['hash'].copy()
    md5.update(egsinp_str.encode('utf-8'))
    base = md5.hexdigest()

    # dose properties
    dose = {
        'egsinp': os.path.join(folder, '{}.egsinp'.format(base)),
        '3ddose': os.path.join(folder, '{}.3ddose'.format(base)),
        'npz': os.path.join(folder, '{}.3ddose.npz'.format(base)),
        'egslst': os.path.join(folder, '{}.egslst'.format(base))
    }

    if not os.path.exists(path):
        # simulate
        remove(dose['3ddose'])
        remove(dose['npz'])
        with open(dose['egsinp'], 'w') as f:
            f.write(egsinp_str)
        command = ['dosxyznrc', '-p', args.pegs4, '-i', os.path.basename(dose['egsinp'])]
        out = await run_command(command, cwd=folder)
        if 'Warning' in out:
            logger.info('Warning in {}'.format(dose['egslst']))
        with open(dose['egslst'], 'w') as f:
            f.write(out)

        # generate npz file
        await read_3ddose(dose['3ddose'])  # use side effect of generating npz
        remove(dose['3ddose'])  # save some space now we have npz
        await copy(dose['npz'], path)
    return dose


def dose_angles(args):
    # recall that 180 theta is center
    # and we do (theta, phi)
    # we just want pairs of phimin and phimax
    angular_increment = 5  # degrees
    angular_sweep = 120  # degrees
    n_angles = angular_sweep // angular_increment
    angles = []
    for i in range(n_angles):
        angles.append((120 + i * angular_increment, 120 + (i + 1) * angular_increment))
    return angles
