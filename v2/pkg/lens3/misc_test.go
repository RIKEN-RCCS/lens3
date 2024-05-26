/* Test Golang. */

package lens3

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	//"net/http"
	"time"
	//"reflect"
	"io"
	"os"
	"os/exec"
	"os/signal"
	//"os/user"
	"strings"
	"syscall"
	"testing"
)

func Test_misc(t *testing.T) {
	// check_signal_handling()
	//test_start_process_with_timeout()
	//test_collect_process_output()
	//test_pipe_timeout()
	//test_get_lines()

	// check_type_switch_on_nil()
	// test_minimal_environ()

	// check_json()

	// run_registrar()
	run_service()
}

func Test_reg(t *testing.T) {
	run_registrar(2)
}

func Test_mux(t *testing.T) {
	run_service()
}

func test_minimal_environ() {
	// runtime.GOMAXPROCS(runtime.NumCPU())

	fmt.Println("test_minimal_environ")
	fmt.Println("minimal_environ()=", minimal_environ())
}

func check_type_switch_on_nil() {
	fmt.Println("check_type_switch_on_nil")
	var x error
	x = nil
	switch e := x.(type) {
	case *exec.ExitError:
		fmt.Print("e=", e)
	case nil:
		fmt.Print("e=", e)
	}
}

func check_signal_handling() {
	fmt.Println("check_signal_handling")
	fmt.Println("Catch INT/TERM; Stop by QUIT")

	var sig = make(chan bool)
	var loop = make(chan error)

	go signal_handler(sig)

	var int_or_term bool
	for {
		go func() {
			time.Sleep(3000 * time.Millisecond)
			loop <- nil
		}()

		select {
		case int_or_term = <-sig:
			fmt.Println("signal int_or_term=", int_or_term)
		case <-loop:
			fmt.Println("timer")
		}
	}
	fmt.Println("done unexpectedly")
}

func signal_handler(chq chan bool) {
	fmt.Println("signal_handler start")

	var ch1 = make(chan os.Signal, 1)
	signal.Notify(ch1, syscall.SIGINT, syscall.SIGTERM, syscall.SIGHUP)

	//var quit bool
	for signal := range ch1 {
		switch signal {
		case syscall.SIGINT:
			fmt.Println("SIGINT")
			chq <- true
		case syscall.SIGTERM:
			fmt.Println("SIGTERM")
			chq <- false
		case syscall.SIGHUP:
			fmt.Println("SIGHUP")
			os.Exit(0)
		}
	}
}

func test_start_process_with_timeout() {
	fmt.Println("test_start_process_with_timeout")

	var server_start_timeout = 1000 * time.Millisecond
	var ctx, cancel = context.WithTimeout(context.Background(),
		server_start_timeout)
	defer cancel()
	var cmd = exec.CommandContext(ctx, "sleep", "5")
	var err = cmd.Run()
	if err != nil {
		fmt.Println("cmd.Run() errs")
	}
	select {
	case <-ctx.Done():
		fmt.Println("ctx.Done()")
		fmt.Println(ctx.Err())
	}
}

func test_collect_process_output() {
	fmt.Println("test_collect_process_output")

	/* cmd.CombinedOutput should be called before Run. */
	/* cmd.CombinedOutput implies Run. */

	var ctx = context.Background()
	var cmd = exec.CommandContext(ctx, "head", "-2", "./LICENSE")

	var outs, errs bytes.Buffer
	cmd.Stdout = &outs
	cmd.Stderr = &errs

	//var outs, err2 = cmd.CombinedOutput()
	//if err2 != nil {
	//	fmt.Println("cmd.CombinedOutput() errs")
	//	panic(err2)
	//}
	//fmt.Println("combined", string(outs))

	var err1 = cmd.Run()
	if err1 != nil {
		fmt.Println("cmd.Run() errs", err1)
	}
	fmt.Println("outs=", outs.String())
	fmt.Println("errs=", errs.String())
}

func test_pipe_timeout() {
	fmt.Println("test_pipe_timeout")

	var ctx = context.Background()
	var cmd = exec.CommandContext(ctx, "head", "-2", "./LICENSE")

	o1, err1 := cmd.StdoutPipe()
	if err1 != nil {
		panic(err1)
	}
	//os.SetReadDeadline(time.Now().Add(10 * time.Second))
	e2, err2 := cmd.StderrPipe()
	if err2 != nil {
		panic(err2)
	}
	//var err3 = cmd.Run()
	var err3 = cmd.Start()
	if err3 != nil {
		fmt.Println("cmd.Start() errs", err3)
	}
	io.Copy(os.Stdout, strings.NewReader("aho aho\n"))
	io.Copy(os.Stdout, o1)
	io.Copy(os.Stdout, e2)
	io.Copy(os.Stdout, strings.NewReader("aho aho\n"))
	//os.Stdout.Flush()
	var err4 = cmd.Wait()
	if err4 != nil {
		fmt.Println("cmd.Wait()", err4)
	}
}

// Do exec.Command(), cmd.StdoutPipe(), bufio.NewScanner().
func test_get_lines() {
	fmt.Println("test_get_lines")

	var ch1 = make(chan string)

	var ctx = context.Background()
	var cmd = exec.CommandContext(ctx, "cat", "./LICENSE")
	if cmd == nil {
		panic("cmd=nil")
	}

	var o1, err1 = cmd.StdoutPipe()
	if err1 != nil {
		log.Fatal(err1)
	}
	//var e2, err2 = cmd.StderrPipe()
	//if err2 != nil {
	//log.Fatal(err2)
	//}
	var err3 = cmd.Start()
	if err3 != nil {
		fmt.Println("cmd.Start() errs", err3)
	}

	go func() {
		for {
			var s1, ok1 = <-ch1
			if !ok1 {
				fmt.Println("CLOSED")
				break
			}
			fmt.Println("LINE: ", s1)
		}
	}()

	var sc = bufio.NewScanner(o1)
	for sc.Scan() {
		//var bs = bytes.Clone(sc.Bytes())
		var s2 = sc.Text()
		//fmt.Println("line: ", s2)
		ch1 <- s2
	}
	close(ch1)
}

func test_functions_in_utility_go() {
	fmt.Println("Check sorting strings...")
	var x1 = string_sort([]string{"jkl", "ghi", "def", "abc"})
	fmt.Println("sorted strings=", x1)

	fmt.Println("")
	fmt.Println("Check string-set equal...")
	var s1 = []string{
		"uid", "modification_time", "groups", "enabled", "claim",
	}
	var s2 = string_sort([]string{
		"uid", "claim", "groups", "enabled", "modification_time",
	})
	var eq = string_set_equal(s1, s2)
	fmt.Println("equal=", eq)
}

func check_json() {
	fmt.Println("Check json on [][2]int strings...")

	// marshaling result:
	// {"F1":[[10,20],[30,40],[40,50]],"F2":[[10,20],[30,40],[40,50]],
	// "F3":null,"F4":null,
	// "F5":[],"F6":[],
	// "F7":[[0,0]],"F8":[[0,0]]}
	// {[[10 20] [30 40] [40 50]] 0xc000012258
	// [] <nil>
	// [] 0xc000012288
	// [[0 0]] 0xc0000122b8}
	// F1 = [[10 20] [30 40] [40 50]] : [][2]int
	// F2 = &[[10 20] [30 40] [40 50]] : *[][2]int
	// F3 = [] : [][2]int
	// F4 = <nil> : *[][2]int
	// F5 = [] : [][2]int
	// F6 = &[] : *[][2]int
	// F7 = [[0 0]] : [][2]int
	// F8 = &[[0 0]] : *[][2]int

	type S1 struct {
		//F1string string
		F1 [][2]int
		F2 *[][2]int
		F3 [][2]int
		F4 *[][2]int
		F5 [][2]int
		F6 *[][2]int
		F7 [][2]int
		F8 *[][2]int
	}
	var x1 = S1{
		F1: [][2]int{{10, 20}, {30, 40}, {40, 50}},
		F2: &[][2]int{{10, 20}, {30, 40}, {40, 50}},
		//F3:
		//F4:
		F5: [][2]int{},
		F6: &[][2]int{},
		F7: [][2]int{{}},
		F8: &[][2]int{{}},
	}
	var b1, err1 = json.Marshal(x1)
	if err1 != nil {
		panic(err1)
	}
	fmt.Println("json marshal", string(b1))
	var x2 S1
	var err2 = json.Unmarshal(b1, &x2)
	if err2 != nil {
		panic(err2)
	}
	fmt.Println("json unmarshal", x2)
	fmt.Printf("F1 = %v : %T\n", x2.F1, x2.F1)
	fmt.Printf("F2 = %v : %T\n", x2.F2, x2.F2)
	fmt.Printf("F3 = %v : %T\n", x2.F3, x2.F3)
	fmt.Printf("F4 = %v : %T\n", x2.F4, x2.F4)
	fmt.Printf("F5 = %v : %T\n", x2.F5, x2.F5)
	fmt.Printf("F6 = %v : %T\n", x2.F6, x2.F6)
	fmt.Printf("F7 = %v : %T\n", x2.F7, x2.F7)
	fmt.Printf("F8 = %v : %T\n", x2.F8, x2.F8)
}
