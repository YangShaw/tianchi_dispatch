#coding=utf-8
'''
Created on Jun 25, 2018

@author: Heng.Zhang
'''

from MachineRes import *
from AppRes import *
from global_param import *
from OfflineJob import *

class MachineRunningInfo(object):
    def __init__(self, each_machine, job_set):
        self.running_machine_res = MachineRes(each_machine)  # 剩余的资源
        self.machine_res = MachineRes(each_machine) # 机器的资源
        self.running_inst_list = []
        self.running_app_dict = {}        
        
        # 每个 app 迁出后所减少的分数
        self.migrating_delta_score_dict = {}
        
        self.running_offline_job_inst_dict = {}
        
        self.cpu_per = self.machine_res.cpu * g_min_cpu_left_useage_per[job_set]
        
        return
    
    def set_cpu_per(self, min_cpu_left_useage_per):
        self.cpu_per = self.machine_res.cpu * min_cpu_left_useage_per
    
    def calculate_migrating_delta_score(self, app_res_dict):
        for app_id in self.running_app_dict.keys():
            app_res = app_res_dict[app_id]
            tmp = self.running_machine_res.get_cpu_slice() + app_res.get_cpu_slice() # app 迁出后， 剩余的cpu 容量增加
            score = score_of_cpu_percent_slice((self.machine_res.cpu - tmp) / self.machine_res.cpu, len(self.running_inst_list))
            self.migrating_delta_score_dict[app_id] = self.get_machine_real_score() - score
        return
    
    def is_heavy_load(self):
        cpu_slice = self.running_machine_res.get_cpu_slice()
        cpu = self.machine_res.cpu
        
        return np.all(cpu_slice > cpu * 0.5)
    
    # 得到启发式信息: 1 / 剩余 cpu 的均值
    def get_heuristic(self, app_res):
        return 1 / (self.running_machine_res.get_cpu_mean() - app_res.get_cpu_mean())    
    
    # ratio 为 1 或 -1，  dispatch app 时 为 -1， 释放app时 为 1
    def update_machine_res(self, inst_id, app_res, ratio):
        self.running_machine_res.update_machine_res(app_res, ratio)

        if (ratio == DISPATCH_RATIO):
            self.running_inst_list.append(inst_id)
            if (app_res.app_id not in self.running_app_dict):
                self.running_app_dict[app_res.app_id] = 0

            self.running_app_dict[app_res.app_id] += 1
        else:
            self.running_inst_list.remove(inst_id)

            self.running_app_dict[app_res.app_id] -= 1
            if (self.running_app_dict[app_res.app_id] == 0):
                self.running_app_dict.pop(app_res.app_id)

        self.running_machine_res.calculate_machine_score(len(self.running_inst_list))

        return True
    
    def sort_running_inst_list(self, app_res_dict, inst_app_dict, reverse=False):
        self.running_inst_list = sorted(self.running_inst_list, key=lambda inst_id : app_res_dict[inst_app_dict[inst_id]].get_cpu_mean(), reverse=reverse)

    # 查找机器上的 running inst list 是否有违反约束的 inst
    def any_self_violate_constriant(self, inst_app_dict, app_res_dict, app_constraint_dict):
        for inst_a in self.running_inst_list:
            app_res_a = app_res_dict[inst_app_dict[inst_a]]
            for inst_b in self.running_inst_list:
                app_res_b = app_res_dict[inst_app_dict[inst_b]]
                immmigrate_app_b_running_inst = self.running_app_dict[app_res_b.app_id]

                # 存在 app_a, app_b, k 约束
                if (app_res_a.app_id in app_constraint_dict and app_res_b.app_id in app_constraint_dict[app_res_a.app_id]):
                    if (app_res_a.app_id == app_res_b.app_id):
                        if (immmigrate_app_b_running_inst > app_constraint_dict[app_res_a.app_id][app_res_b.app_id] + 1):                         
                            return inst_b
                    else:
                        if (immmigrate_app_b_running_inst > app_constraint_dict[app_res_a.app_id][app_res_b.app_id]):
                            return inst_b
        return None
    
    def get_machine_id(self):
        return self.machine_res.machine_id

    def print_remaining_res(self, inst_app_dict, app_res_dict):
        for each_inst in self.running_inst_list:
            print(getCurrentTime(), '%s, %s ' % (each_inst, app_res_dict[inst_app_dict[each_inst]].to_string()))
            
        print(getCurrentTime(), self.running_machine_res.to_string())
    
    def get_cpu(self):
        return self.running_machine_res.cpu
    
    def get_cpu_mean(self):
        return self.running_machine_res.cpu_mean
    
    def get_cpu_mean_idx(self):
        return self.running_machine_res.cpu_men_idx

    def get_cpu_percentage(self):
        return max(self.running_machine_res.cpu_percentage - 0.5, 0) # cpu 使用率低于0.5 的归为一类 6027
#         return self.running_machine_res.cpu_percentage

    def get_machine_score(self):
        return max(self.running_machine_res.machine_score - 196, 0) # 得分低于 196 的归为一类

    def get_machine_real_score(self):
        return self.running_machine_res.machine_score
    
    # 查看机器总的资源是否能容纳 app
    def meet_inst_res_require(self, app_res):
        return self.machine_res.meet_inst_res_require(app_res)
    
    # 如果符合约束，则可以迁入，则 app_B_running_inst 会 +1， 所以这里用 <, 不能用 <=
    def check_if_meet_A_B_constraint(self, app_A_id, app_B_id, app_B_running_inst, app_constraint_dict):
        if (app_A_id in app_constraint_dict and app_B_id in app_constraint_dict[app_A_id]):
            if (app_A_id == app_B_id):
                return app_B_running_inst < app_constraint_dict[app_A_id][app_B_id] + 1
            else:
                return app_B_running_inst < app_constraint_dict[app_A_id][app_B_id]

        return True
        
    
    # 迁入 app_res 是否满足约束条件
    def meet_constraint(self, app_res, app_constraint_dict):
        # 需要迁入的 app 在当前机器上运行的实例数
        immmigrate_app_running_inst = 0
        if (app_res.app_id in self.running_app_dict):
            immmigrate_app_running_inst = self.running_app_dict[app_res.app_id]

        # 在当前机器上运行的 app 与需要迁入的 app 是否有约束，有约束的话看 immmigrate_app_running_inst 是否满足约束条件
        # 不满足约束的情况下 1. 不能部署在当前机器上，  2. 迁移走某些 app 使得可以部署
        # 当前先实现 1
        for app_id, inst_cnt in self.running_app_dict.items():
            if (not self.check_if_meet_A_B_constraint(app_A_id = app_id, 
                                                      app_B_id = app_res.app_id, 
                                                      app_B_running_inst = immmigrate_app_running_inst,
                                                      app_constraint_dict=app_constraint_dict)):
                return False

            if (not self.check_if_meet_A_B_constraint(app_A_id = app_res.app_id, 
                                                      app_B_id = app_id,
                                                      app_B_running_inst = inst_cnt,
                                                      app_constraint_dict = app_constraint_dict)):
                return False

        return True
    
    # 迁入一个 app list 是否满足约束条件
    def meet_constraint_ex(self, inst_list, inst_app_dict, app_res_dict, app_constraint_dict):
        tmp_running_app_dict = self.running_app_dict.copy()

        for each_inst in inst_list:
            app_res = app_res_dict[inst_app_dict[each_inst]]
            # 需要迁入的 app 在当前机器上运行的实例数
            immmigrate_app_running_inst = 0
            if (app_res.app_id in tmp_running_app_dict):
                immmigrate_app_running_inst = tmp_running_app_dict[app_res.app_id]
    
            # 在当前机器上运行的 app 与需要迁入的 app 是否有约束，有约束的话看 immmigrate_app_running_inst 是否满足约束条件
            # 不满足约束的情况下 1. 不能部署在当前机器上，  2. 迁移走某些 app 使得可以部署
            # 当前先实现 1
            for app_id, inst_cnt in tmp_running_app_dict.items():
                if (not self.check_if_meet_A_B_constraint(app_A_id = app_id, 
                                                          app_B_id = app_res.app_id, 
                                                          app_B_running_inst = immmigrate_app_running_inst,
                                                          app_constraint_dict = app_constraint_dict)):
                    return False
    
                if (not self.check_if_meet_A_B_constraint(app_A_id = app_res.app_id, 
                                                          app_B_id = app_id,
                                                          app_B_running_inst = inst_cnt,
                                                          app_constraint_dict = app_constraint_dict)):
                    return False
    
            # 要迁入的 app_res.app_id 都符合 running inst 的约束
            if (app_res.app_id not in tmp_running_app_dict):
                tmp_running_app_dict[app_res.app_id] = 0

            tmp_running_app_dict[app_res.app_id] += 1

        return True

    # 是否可以将 app_res_list 分发到当前机器
    def can_dispatch_ex(self, inst_list, inst_app_dict, app_res_dict, app_constraint_dict):
        if (not self.meet_constraint_ex(inst_list, inst_app_dict, app_res_dict, app_constraint_dict)):
            return False
        
        tmp_app_res = AppRes.sum_app_res_by_inst(inst_list, inst_app_dict, app_res_dict)
        
        # 满足约束条件，看剩余资源是否满足
        return self.running_machine_res.meet_inst_res_require(tmp_app_res)

    # 是否可以将 app_res 分发到当前机器
    def can_dispatch(self, app_res, app_constraint_dict):
        # 剩余资源是否满足
        if (not self.running_machine_res.meet_inst_res_require(app_res)):
            return False

        # 是否满足约束条件
        return self.meet_constraint(app_res, app_constraint_dict) 

    def dispatch_app(self, inst_id, app_res, app_constraint_dict):
        if (self.can_dispatch(app_res, app_constraint_dict)):
            self.update_machine_res(inst_id, app_res, DISPATCH_RATIO)
            return True

        return False
    
    # 将 app 迁出后所减少的分数
    def migrating_delta_score_ex(self, app_res):
        return self.migrating_delta_score_dict[app_res.app_id]

    def migrating_delta_score(self, app_res):
        tmp = self.running_machine_res.get_cpu_slice() + app_res.get_cpu_slice() # app 迁出后， 剩余的cpu 容量增加
         
        score = score_of_cpu_percent_slice((self.machine_res.cpu - tmp) / self.machine_res.cpu, len(self.running_inst_list))
        return self.get_machine_real_score() - score
    

    # 将 app 迁出后的分数
    def migrating_score(self, app_res):
        tmp = self.running_machine_res.get_cpu_slice() + app_res.get_cpu_slice() # app 迁出后， 剩余的cpu 容量增加
        score = score_of_cpu_percent_slice((self.machine_res.cpu - tmp) / self.machine_res.cpu, len(self.running_inst_list))
        
        return score
    
    
    # 将 app 迁入后的分数
    def immigrating_score(self, app_res):
        tmp = self.running_machine_res.get_cpu_slice() - app_res.get_cpu_slice() # app 迁入后， 剩余的cpu 容量减少
        tmp = np.where(np.less(tmp, 0.001), 0, tmp) # slice 由于误差可能不会为0， 这里凡是 < 0.001 的 slice 都设置成0
        score = score_of_cpu_percent_slice((self.machine_res.cpu - tmp) / self.machine_res.cpu, len(self.running_inst_list))
        
        return score
    
    # 将 app 迁入后所增加的分数
    def immigrating_delta_score(self, app_res):
        tmp = self.running_machine_res.get_cpu_slice() - app_res.get_cpu_slice() # app 迁入后， 剩余的cpu 容量减少
        tmp = np.where(np.less(tmp, 0.001), 0, tmp) # slice 由于误差可能不会为0， 这里凡是 < 0.001 的 slice 都设置成0
        score = score_of_cpu_percent_slice((self.machine_res.cpu - tmp) / self.machine_res.cpu, len(self.running_inst_list))
        return score - self.get_machine_real_score()   
    
    def release_app(self, inst_id, app_res):
        if (inst_id in self.running_inst_list):
            self.update_machine_res(inst_id, app_res, RELEASE_RATIO)
            return True

        return False

    # 为了将  immgrate_inst_id 迁入， 需要将 running_inst_list 中的一个或多个 inst 迁出，
    # 迁出的规则为： 满足迁入app cpu 的最小值，迁出的 app 越多越好，越多表示迁出的 app cpu 越分散，迁移到其他机器上也就越容易
    def cost_of_immigrate_app(self, immgrate_inst_id, inst_app_dict, app_res_dict, app_constraint_dict):
       
        start_time = time.time()
        candidate_apps_list_of_machine = []
        # 候选 迁出  inst list 的长度从 1 到 len(self.runing_app_list)
        candidate_insts = self.running_inst_list.copy()
        for inst_list_size in range(1, len(candidate_insts) + 1):
            app_list_at_size = []
            end_idx_of_running_set = len(candidate_insts) - inst_list_size + 1 
            for i in range(end_idx_of_running_set): 
                cur_inst_list = [candidate_insts[i]]
                self.find_migratable_app(cur_inst_list, inst_list_size - 1, i + 1, candidate_insts, \
                                         app_list_at_size, immgrate_inst_id, \
                                         inst_app_dict, app_res_dict, app_constraint_dict)

            candidate_apps_list_of_machine.extend(app_list_at_size)
            # 若 inst 出现在长度为 n 的候选迁出列表中，则该 inst 不会出现在长度为 n+1 的列表中， 将 inst 从候选列表中删除，
            # 这样可以极大地减小枚举的数量
            for each_list in app_list_at_size:               
                for each_inst in each_list:
                    candidate_insts.remove(each_inst)

            # len(candidate_insts) <= inst_list_size , inst_list_size 为已经枚举完毕的长度，下次循环会+1， 所以这里是 <=
            if (len(candidate_insts) == 0 or len(candidate_insts) <= inst_list_size):
                break

        # 在所有符合条件的可迁出 app list 中， 找到在当前机器上得分最低的作为迁出列表
        if (len(candidate_apps_list_of_machine) > 0):
            min_score = 1e9
            min_idx = 0
            for i, each_candidate_list in enumerate(candidate_apps_list_of_machine):
                tmp_app = AppRes.sum_app_res_by_inst(each_candidate_list, inst_app_dict, app_res_dict)
                score_of_list = self.migrating_delta_score(tmp_app)
                if (score_of_list < min_score):
                    min_score = score_of_list
                    min_idx = i

            end_time = time.time()
            
            print(getCurrentTime(), " done, running inst len %d, ran %d seconds" % \
                  (len(self.running_inst_list), end_time - start_time))

            return candidate_apps_list_of_machine[min_idx], min_score
        else:
            return []
        
    # 在 running_inst_list 的 [start_idx, end_idx) 范围内， 找到一个 app_list_size 长度的 app_list, 
    # 使得 app_list 的 cpu 满足迁入的  app cpu， 保存起来作为迁出的 app list 候选
    def find_migratable_app(self, cur_inst_list, left_inst_list_size, start_idx, candidate_insts,
                            candidate_apps_list, immgrate_inst_id, inst_app_dict, app_res_dict, app_constraint_dict):
        if (left_inst_list_size == 0):
            # 将要迁出的资源之和
            tmp_app_res = AppRes.sum_app_res_by_inst(cur_inst_list, inst_app_dict, app_res_dict)

            # 候选的迁出 app list 资源加上剩余的资源 满足迁入的  app cpu， 保存起来作为迁出的 app list 候选
            immigrating_app_res = app_res_dict[inst_app_dict[immgrate_inst_id]]
            if (np.all(tmp_app_res.get_cpu_slice() + self.running_machine_res.get_cpu_slice() >= immigrating_app_res.get_cpu_slice()) and 
                np.all(tmp_app_res.mem_slice + self.running_machine_res.mem >= immigrating_app_res.mem_slice) and 
                tmp_app_res.disk + self.running_machine_res.disk >= immigrating_app_res.disk and 
                tmp_app_res.p + self.running_machine_res.p >= immigrating_app_res.p and 
                tmp_app_res.m + self.running_machine_res.m >= immigrating_app_res.m and
                tmp_app_res.pm + self.running_machine_res.pm >= immigrating_app_res.pm):
                candidate_apps_list.append(cur_inst_list)
            return 
        
        for i in range(start_idx, len(candidate_insts)):
            self.find_migratable_app(cur_inst_list + [candidate_insts[i]], left_inst_list_size - 1, i + 1, candidate_insts,
                                     candidate_apps_list, immgrate_inst_id, inst_app_dict, app_res_dict, app_constraint_dict)
        return
    
    def get_cpu_slice_by_index(self, offlineJob, current_slice):
        usable_cpu_slice = self.running_machine_res.get_cpu_slice()[current_slice: current_slice + offlineJob.run_mins]
        return usable_cpu_slice
    
    def get_mem_slice_by_index(self, offlineJob, current_slice):        
        usable_mem_slice = self.running_machine_res.get_mem_slice()[current_slice: current_slice + offlineJob.run_mins]
        return usable_mem_slice
    
    # 在 cpu_per 的情况下是否可以至少可以分发一个 job inst
    def can_dispatch_offline_job(self, offlineJob, current_slice):
        if (current_slice + offlineJob.run_mins >= SLICE_CNT):
            return False

        usable_cpu_slice = self.get_cpu_slice_by_index(offlineJob, current_slice) - self.cpu_per
        usable_mem_slice = self.get_mem_slice_by_index(offlineJob, current_slice)
        
        return (np.all(usable_cpu_slice >= offlineJob.cpu) and 
                np.all(usable_mem_slice >= offlineJob.mem))
        

    # 在 [current slice, offlineJob.run_min) 范围内无法分发 offlineJob 的情况下，
    # 找到从 [current slice, offlineJob.run_min) 内的下一个搜索位置    
    def get_seek_next(self, offlineJob, current_slice):
        usable_cpu_slice = self.get_cpu_slice_by_index(offlineJob, current_slice) - self.cpu_per
        usable_mem_slice = self.get_mem_slice_by_index(offlineJob, current_slice)
        
        for slice_idx in range(offlineJob.run_mins - 1, -1, -1):
            if (usable_cpu_slice[slice_idx] < offlineJob.cpu or usable_mem_slice[slice_idx] < offlineJob.mem):
                return current_slice + slice_idx + 1

        return current_slice + slice_idx + 1# 应该不会走到这里

    # 从 current_slice 开始， 找到能够分发 offline job 的最早的 slice
    def seek_min_dispatchable_slice(self, offlineJob, current_slice):
#         cpu_slice = self.running_machine_res.get_cpu_slice()
#         mem_slice = self.running_machine_res.get_mem_slice()
        min_dispatchable_slice = current_slice
        
        # 从最小完成时间之后开始查找可以分发 offline job 的 slice
        while (min_dispatchable_slice + offlineJob.run_mins < SLICE_CNT):
            if (self.can_dispatch_offline_job(offlineJob, min_dispatchable_slice)):
                break
            
            min_dispatchable_slice = self.get_seek_next(offlineJob, min_dispatchable_slice)

#             while (min_dispatchable_slice + offlineJob.run_mins < SLICE_CNT):
#                 if (cpu_slice[min_dispatchable_slice] - self.cpu_per >= offlineJob.cpu and 
#                     mem_slice[min_dispatchable_slice] >= offlineJob.mem):
#                     break
#                 min_dispatchable_slice += 1

        if (min_dispatchable_slice + offlineJob.run_mins < SLICE_CNT):
            return min_dispatchable_slice 

        return SLICE_CNT     
    
    # 从 current_slice 开始， 找到能够分发 offline job 的最早的 slice, 以及可以分发的 inst 的数量
    def seek_min_dispatchable_slice_and_cnt(self, offlineJob, current_slice):
        cpu_slice = self.running_machine_res.get_cpu_slice()
        mem_slice = self.running_machine_res.get_mem_slice()
        min_dispatchable_slice = current_slice
        
        # 从最小完成时间之后开始查找可以分发 offline job 的 slice
        while (min_dispatchable_slice + offlineJob.run_mins < SLICE_CNT):
            if (self.can_dispatch_offline_job(offlineJob, min_dispatchable_slice)):
                break
            
            min_dispatchable_slice += 1
            while (min_dispatchable_slice + offlineJob.run_mins < SLICE_CNT):
                if (cpu_slice[min_dispatchable_slice] - self.cpu_per >= offlineJob.cpu and 
                    mem_slice[min_dispatchable_slice] >= offlineJob.mem):
                    break
                min_dispatchable_slice += 1

        if (min_dispatchable_slice + offlineJob.run_mins < SLICE_CNT):
            dispatch_cnt = self.get_dispatch_offline_inst_cnt(offlineJob, min_dispatchable_slice)
            return min_dispatchable_slice, dispatch_cnt
        else:
            return SLICE_CNT, 0
    
    def get_dispatch_offline_inst_cnt(self, offlineJob, current_slice):
        if (not self.can_dispatch_offline_job(offlineJob, current_slice)):
            return 0
        
        # 在cpu 剩余容量不低于 cpu_per 的情况下， 看能分发多少个 job inst
        machine_cpu_slice = self.get_cpu_slice_by_index(offlineJob, current_slice) - self.cpu_per
        if (np.any(machine_cpu_slice <= 0)):
            return 0 

        # 能分发多少个 job inst
        dispatchable_inst_cnt = min(machine_cpu_slice.min() // offlineJob.cpu, offlineJob.inst_cnt)
        
        return dispatchable_inst_cnt 


    # 在 current_slice 上是否能够分发 offline job, 能分发多少个
    def dispatch_offline_job(self, offlineJob, current_slice):
        # 能分发多少个 job inst
        dispatchable_inst_cnt = self.get_dispatch_offline_inst_cnt(offlineJob, current_slice)

        if (dispatchable_inst_cnt > 0):
            self.update_machine_res_offline(offlineJob, current_slice, dispatchable_inst_cnt, DISPATCH_RATIO)

        return dispatchable_inst_cnt

    def dispatch_offline_job_one(self, offlineJob, current_slice):
        if (self.can_dispatch_offline_job(offlineJob, current_slice)):  
            self.update_machine_res_offline(offlineJob, current_slice, 1, DISPATCH_RATIO)
            return 1
        else:
            return 0
    
    
    #  释放机器 的 cpu， mem 的 [current_slice, current_slice + offlineJob.run_mins) 区间, 释放 inst_cnt 个实例
    def release_offline_job(self, offlineJob, current_slice, inst_cnt):    
        return self.update_machine_res_offline(offlineJob, current_slice, inst_cnt, RELEASE_RATIO)

        
    def update_machine_res_offline(self, offlineJob, current_slice, inst_cnt, ratio):
        self.running_machine_res.update_machine_res_offline(offlineJob, current_slice, inst_cnt, ratio)
        self.running_machine_res.calculate_machine_score(len(self.running_inst_list))
        
        if (ratio == DISPATCH_RATIO):
            if (not offlineJob.job_id in self.running_offline_job_inst_dict):
                self.running_offline_job_inst_dict[offlineJob.job_id] = [] 
    
            self.running_offline_job_inst_dict[offlineJob.job_id].append([inst_cnt, current_slice])  # inst 数量， 启动时间
            return True
        else:
            pop_idx = -1
            offlinejob_dispatch_list = self.running_offline_job_inst_dict[offlineJob.job_id]
            for i in range(len(offlinejob_dispatch_list)):
                if (offlinejob_dispatch_list[i][0] == inst_cnt and 
                    offlinejob_dispatch_list[i][1] == current_slice):
                    pop_idx = i
                    break
            if (pop_idx >= 0):
                offlinejob_dispatch_list.pop(pop_idx)

                if (len(offlinejob_dispatch_list) == 0):
                    self.running_offline_job_inst_dict.pop(offlineJob.job_id)
                
                return True
            
            return False

        
    # 得到 current_slice 之后的 running finishe job 的最小完成时间
    def running_offline_min_finish_slice(self, offlineJob_dict, current_slice):
        min_dispatchable_slice = 1e9
        
        for job_id in self.running_offline_job_inst_dict.keys():
            finish_slice = self.running_offline_job_inst_dict[job_id][1] + offlineJob_dict[job_id].run_mins # 启动时间 + 运行时间 
            if (finish_slice > current_slice and finish_slice < min_dispatchable_slice):
                min_dispatchable_slice = finish_slice

        return min_dispatchable_slice
    
    # 找到 offlineJob 的 prefix job 的最后完成时间 
    def get_max_prefix_finish_slice(self, offlineJob, offlineJob_dict):
        max_finish_slice = 0
        for job_id in self.running_offline_job_inst_dict.keys():
            if (job_id not in offlineJob.prefix_jobs):
                continue
            
            offlinejob_dispatch_list = self.running_offline_job_inst_dict[job_id]
            for each_disp in offlinejob_dispatch_list:
                finish_slice = each_disp[1] + offlineJob_dict[job_id].run_mins # 启动时间 + 运行时间
                if (max_finish_slice < finish_slice):
                    max_finish_slice = finish_slice

        return max_finish_slice
    
    # 迁移出哪些 inst，  cpu 可以 <= 0.5
    def get_overload_inst_list(self, app_res_dict, inst_app_dict):
        running_inst_list = sorted(self.running_inst_list, key=lambda inst_id : app_res_dict[inst_app_dict[inst_id]].get_cpu_mean(), reverse=True)
        real_score = self.get_machine_real_score()
        for i in range(0, len(running_inst_list)):
            tmp_app_res = AppRes.sum_app_res_by_inst(running_inst_list[:i + 1], inst_app_dict, app_res_dict)
            delta_score = self.migrating_delta_score(tmp_app_res)
            if (real_score - delta_score < SLICE_CNT):
                return running_inst_list[:i + 1]
            
        return running_inst_list
            

    # 返回 cpu 最高的 n 个 inst
    def get_max_cpu_inst_list(self, app_res_dict, inst_app_dict, n):        
        running_inst_list = sorted(self.running_inst_list, key=lambda inst_id : app_res_dict[inst_app_dict[inst_id]].get_cpu_mean(), reverse=True)
        
        if (len(running_inst_list) <= n):
            return running_inst_list

        return running_inst_list[:n]





        