package fixture;
import org.springframework.stereotype.Service;
@Service class Entry {
    static class Replacement extends Entry { public void work() {} }
    public void run() { work(); }
    public void work() {}
}
